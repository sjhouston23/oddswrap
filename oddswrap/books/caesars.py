"""Caesars Sportsbook adapter (americanwagering.com API)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, Sport, decimal_to_american, normalize_start_time, parse_american

logger = logging.getLogger("oddswrap.caesars")

# Caesars competition IDs (UUIDs) per sport
_COMPETITION_IDS: dict[Sport, str] = {
    Sport.MLB: "04f90892-3afa-4e84-acce-5b89f151063d",
    Sport.NBA: "5806c896-4eec-4de1-874f-afed93114b8c",
    Sport.NFL: "007d7c61-07a7-4e18-bb40-15104b6eac92",
    Sport.NHL: "b7b715a9-c7e8-4c47-af0a-77385b525e09",
}

_SPORT_IDS: dict[Sport, str] = {
    Sport.MLB: "baseball",
    Sport.NBA: "basketball",
    Sport.NFL: "americanfootball",
    Sport.NHL: "icehockey",
}

_BASE_URL = (
    "https://api.americanwagering.com/regions/us/locations/{state}/brands/czr/sb/v3/sports/{sport_id}/events/schedule"
)

# Market type mappings (lowercased, pipe-stripped for matching)
_MONEYLINE_TYPES = {"moneyline", "money line", "head to head"}
_SPREAD_TYPES = {"run line", "point spread", "spread", "puck line", "handicap"}
_TOTAL_TYPES = {"total runs", "total points", "total goals", "total", "over/under", "totals"}


def _parse_odds(selection: dict) -> int | None:
    """Extract American odds from a Caesars selection's price object."""
    price = selection.get("price", {})
    # Try American odds first (field 'a'), fall back to 'd' (decimal)
    american = price.get("a")
    if american is not None:
        val = parse_american(str(american))
        if val is not None:
            return val
    dec = price.get("d")
    if dec is not None:
        try:
            return decimal_to_american(float(dec))
        except (ValueError, TypeError):
            return None
    return None


def _parse_handicap(val) -> float | None:
    """Parse handicap/line value."""
    if val is None:
        return None
    try:
        return float(str(val))
    except (ValueError, TypeError):
        return None


def _clean_name(name: str) -> str:
    """Strip Caesars pipe delimiters from names."""
    return name.strip().strip("|").strip()


class CaesarsAdapter(BookAdapter):
    name = "caesars"

    def __init__(self, state: str = "nj"):
        self._state = state

    def supported_sports(self) -> list[Sport]:
        return list(_COMPETITION_IDS.keys())

    def _fetch_raw(self, sport: Sport) -> list[dict] | None:
        comp_id = _COMPETITION_IDS.get(sport)
        sport_id = _SPORT_IDS.get(sport)
        if comp_id is None or sport_id is None:
            return None
        url = _BASE_URL.format(state=self._state, sport_id=sport_id)
        try:
            resp = cffi_requests.get(
                url,
                params={"competitionIds": comp_id},
                impersonate="chrome120",
                headers={"Accept": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            competitions = data.get("competitions", [])
            if competitions:
                return competitions[0].get("events", [])
            return []
        except Exception as exc:
            logger.warning("Caesars fetch failed for %s: %s", sport, exc)
            return None

    def _get_teams(self, event: dict) -> tuple[str, str] | None:
        """Extract (away_team, home_team) from event."""
        # Try competitors array first
        competitors = event.get("competitors", [])
        home = away = None
        for comp in competitors:
            ctype = comp.get("type", "").upper()
            name = comp.get("name", "")
            if not name:
                continue
            if ctype == "HOME":
                home = name
            elif ctype == "AWAY":
                away = name
        if home and away:
            return away, home

        # Fallback: parse from event name (supports "|at|", "@", "vs" separators)
        name = event.get("name", "")
        for sep in [" |at| ", " | vs | ", " @ ", " vs ", " v "]:
            if sep in name:
                parts = name.split(sep, 1)
                if len(parts) == 2:
                    return _clean_name(parts[0]), _clean_name(parts[1])
        return None

    def _get_markets(self, event: dict, market_types: set[str]) -> list[dict]:
        """Filter markets by type name within an event."""
        markets = []
        for mkt in event.get("markets", []):
            if not mkt.get("active", True) or not mkt.get("display", True):
                continue
            # Handle pipe-delimited names: "|Moneyline|" → "moneyline"
            raw_name = mkt.get("displayName") or mkt.get("name", "")
            mkt_name = _clean_name(raw_name).lower()
            if mkt_name in market_types:
                markets.append(mkt)
        return markets

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        events = self._fetch_raw(sport)
        if not events:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for event in events:
            teams = self._get_teams(event)
            if not teams:
                continue
            away_name, home_name = teams

            for mkt in self._get_markets(event, _MONEYLINE_TYPES):
                home_odds = away_odds = None
                for sel in mkt.get("selections", []):
                    name = sel.get("name", "")
                    val = _parse_odds(sel)
                    if val is None:
                        continue
                    if name == home_name or home_name in name or name in home_name:
                        home_odds = val
                    elif name == away_name or away_name in name or name in away_name:
                        away_odds = val

                if home_odds is None and away_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_name,
                        away_team=away_name,
                        start_time=normalize_start_time(event.get("startTime")),
                        game_id=str(event.get("id", "")),
                        lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
                    )
                )

        logger.info("Caesars %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        events = self._fetch_raw(sport)
        if not events:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for event in events:
            teams = self._get_teams(event)
            if not teams:
                continue
            away_name, home_name = teams

            for mkt in self._get_markets(event, _SPREAD_TYPES):
                home_spread = away_spread = None
                home_spread_odds = away_spread_odds = None
                line_val = _parse_handicap(mkt.get("line"))

                for sel in mkt.get("selections", []):
                    name = sel.get("name", "")
                    val = _parse_odds(sel)
                    handicap = _parse_handicap(sel.get("price", {}).get("handicap")) or line_val
                    if val is None:
                        continue
                    if name == home_name or home_name in name or name in home_name:
                        home_spread = handicap
                        home_spread_odds = val
                    elif name == away_name or away_name in name or name in away_name:
                        away_spread = handicap
                        away_spread_odds = val

                # Infer opposite spread if only one side has a handicap
                if home_spread is not None and away_spread is None and away_spread_odds is not None:
                    away_spread = -home_spread
                elif away_spread is not None and home_spread is None and home_spread_odds is not None:
                    home_spread = -away_spread

                if home_spread_odds is None and away_spread_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_name,
                        away_team=away_name,
                        start_time=normalize_start_time(event.get("startTime")),
                        game_id=str(event.get("id", "")),
                        lines=[
                            Line(
                                book=self.name,
                                home_spread=home_spread,
                                away_spread=away_spread,
                                home_spread_odds=home_spread_odds,
                                away_spread_odds=away_spread_odds,
                                fetched_at=now,
                            )
                        ],
                    )
                )

        logger.info("Caesars %s spreads: %d games", sport.value, len(games))
        return games

    # -- Totals --

    def fetch_totals(self, sport: Sport) -> list[Game]:
        events = self._fetch_raw(sport)
        if not events:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for event in events:
            teams = self._get_teams(event)
            if not teams:
                continue
            away_name, home_name = teams

            for mkt in self._get_markets(event, _TOTAL_TYPES):
                total = _parse_handicap(mkt.get("line"))
                over_odds = under_odds = None
                for sel in mkt.get("selections", []):
                    name = sel.get("name", "").lower()
                    val = _parse_odds(sel)
                    if val is None:
                        continue
                    if "over" in name:
                        over_odds = val
                        if total is None:
                            total = _parse_handicap(sel.get("price", {}).get("handicap"))
                    elif "under" in name:
                        under_odds = val
                        if total is None:
                            total = _parse_handicap(sel.get("price", {}).get("handicap"))

                if over_odds is None and under_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_name,
                        away_team=away_name,
                        start_time=normalize_start_time(event.get("startTime")),
                        game_id=str(event.get("id", "")),
                        lines=[
                            Line(
                                book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now
                            )
                        ],
                    )
                )

        logger.info("Caesars %s totals: %d games", sport.value, len(games))
        return games
