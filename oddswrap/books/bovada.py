"""Bovada Sportsbook adapter."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, Sport, normalize_start_time, parse_american

logger = logging.getLogger("oddswrap.bovada")

# Bovada coupon API — sport path per Sport enum
_SPORT_PATHS: dict[Sport, str] = {
    Sport.MLB: "baseball/mlb",
    Sport.NBA: "basketball/nba",
    Sport.NFL: "football/nfl",
    Sport.NHL: "hockey/nhl",
    Sport.NCAAF: "football/college-football",
    Sport.NCAAB: "basketball/college-basketball",
}

_BASE_URL = "https://www.bovada.lv/services/sports/event/coupon/events/A/description/{path}?lang=en"


def _parse_handicap(val) -> float | None:
    """Parse handicap value from price object (string or numeric)."""
    if val is None:
        return None
    try:
        return float(str(val))
    except (ValueError, TypeError):
        return None


def _epoch_ms_to_iso(ts: int | None) -> str | None:
    """Convert epoch milliseconds to ISO 8601 string."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None


def _is_live(event: dict) -> bool:
    """Check if an event is live/in-progress."""
    return event.get("live", False)


def _get_competitors(event: dict) -> tuple[str, str] | None:
    """Extract (away_team, home_team) from competitors array."""
    competitors = event.get("competitors", [])
    home = away = None
    for comp in competitors:
        if comp.get("home"):
            home = comp.get("name")
        else:
            away = comp.get("name")
    if home and away:
        return away, home
    return None


def _find_markets(event: dict, market_desc: str) -> list[dict]:
    """Find all markets matching a description within an event's displayGroups."""
    markets = []
    for dg in event.get("displayGroups", []):
        for mkt in dg.get("markets", []):
            if mkt.get("description") == market_desc and mkt.get("status") == "O":
                markets.append(mkt)
    return markets


class BovadaAdapter(BookAdapter):
    name = "bovada"

    def supported_sports(self) -> list[Sport]:
        return list(_SPORT_PATHS.keys())

    def _fetch_raw(self, sport: Sport) -> list[dict] | None:
        path = _SPORT_PATHS.get(sport)
        if path is None:
            return None
        url = _BASE_URL.format(path=path)
        try:
            resp = cffi_requests.get(url, impersonate="chrome120", timeout=15)
            resp.raise_for_status()
            data = resp.json()
            # Response is a JSON array; events are in the first element
            if isinstance(data, list) and data:
                return data[0].get("events", [])
            return []
        except Exception as exc:
            logger.warning("Bovada fetch failed for %s: %s", sport, exc)
            return None

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        events = self._fetch_raw(sport)
        if events is None:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for event in events:
            teams = _get_competitors(event)
            if not teams:
                continue
            away_raw, home_raw = teams

            for mkt in _find_markets(event, "Moneyline"):
                home_odds = away_odds = None
                for outcome in mkt.get("outcomes", []):
                    if outcome.get("status") != "O":
                        continue
                    desc = outcome.get("description", "")
                    val = parse_american(outcome.get("price", {}).get("american"))
                    if val is None:
                        continue
                    if desc == home_raw:
                        home_odds = val
                    elif desc == away_raw:
                        away_odds = val

                if home_odds is None and away_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_raw,
                        away_team=away_raw,
                        start_time=normalize_start_time(_epoch_ms_to_iso(event.get("startTime"))),
                        game_id=str(event.get("id", "")),
                        live=_is_live(event),
                        lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
                    )
                )

        logger.info("Bovada %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        events = self._fetch_raw(sport)
        if events is None:
            return []
        now = datetime.now(timezone.utc).isoformat()
        market_name = "Runline" if sport == Sport.MLB else "Point Spread"

        games: list[Game] = []
        for event in events:
            teams = _get_competitors(event)
            if not teams:
                continue
            away_raw, home_raw = teams

            for mkt in _find_markets(event, market_name):
                home_spread = away_spread = None
                home_spread_odds = away_spread_odds = None
                for outcome in mkt.get("outcomes", []):
                    if outcome.get("status") != "O":
                        continue
                    desc = outcome.get("description", "")
                    price = outcome.get("price", {})
                    val = parse_american(price.get("american"))
                    handicap = _parse_handicap(price.get("handicap"))
                    if val is None:
                        continue
                    if desc == home_raw:
                        home_spread = handicap
                        home_spread_odds = val
                    elif desc == away_raw:
                        away_spread = handicap
                        away_spread_odds = val

                if home_spread_odds is None and away_spread_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_raw,
                        away_team=away_raw,
                        start_time=normalize_start_time(_epoch_ms_to_iso(event.get("startTime"))),
                        game_id=str(event.get("id", "")),
                        live=_is_live(event),
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

        logger.info("Bovada %s spreads: %d games", sport.value, len(games))
        return games

    # -- Totals --

    def fetch_totals(self, sport: Sport) -> list[Game]:
        events = self._fetch_raw(sport)
        if events is None:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for event in events:
            teams = _get_competitors(event)
            if not teams:
                continue
            away_raw, home_raw = teams

            for mkt in _find_markets(event, "Total"):
                total = None
                over_odds = under_odds = None
                is_full_game = True
                for outcome in mkt.get("outcomes", []):
                    if outcome.get("status") != "O":
                        continue
                    desc = outcome.get("description", "")
                    # Skip inning-specific totals (e.g. "Over - L1H", "Under - L3I")
                    if " - " in desc:
                        is_full_game = False
                        break
                    price = outcome.get("price", {})
                    val = parse_american(price.get("american"))
                    handicap = _parse_handicap(price.get("handicap"))
                    if val is None:
                        continue
                    if desc.lower() == "over":
                        over_odds = val
                        total = handicap
                    elif desc.lower() == "under":
                        under_odds = val
                        if total is None:
                            total = handicap

                if not is_full_game or (over_odds is None and under_odds is None):
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_raw,
                        away_team=away_raw,
                        start_time=normalize_start_time(_epoch_ms_to_iso(event.get("startTime"))),
                        game_id=str(event.get("id", "")),
                        live=_is_live(event),
                        lines=[
                            Line(
                                book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now
                            )
                        ],
                    )
                )

        logger.info("Bovada %s totals: %d games", sport.value, len(games))
        return games
