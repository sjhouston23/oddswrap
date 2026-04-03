"""TheScore Bet Sportsbook adapter (Penn Entertainment platform)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, Sport

logger = logging.getLogger("oddswrap.thescore")

# TheScore sport slugs and competition paths
_SPORT_PATHS: dict[Sport, str] = {
    Sport.MLB: "baseball/organization/united-states/competition/mlb",
    Sport.NBA: "basketball/organization/united-states/competition/nba",
    Sport.NFL: "football/organization/united-states/competition/nfl",
    Sport.NHL: "hockey/organization/united-states/competition/nhl",
}

_BASE_URL = "https://sb-content.thescore.bet/content/sportsbook/v1"


def _parse_american(val) -> int | None:
    if val is None:
        return None
    try:
        return int(str(val).replace("\u2212", "-"))
    except (ValueError, TypeError):
        return None


def _decimal_to_american(decimal_odds: float) -> int | None:
    """Convert decimal odds to American format."""
    if decimal_odds is None or decimal_odds <= 1.0:
        return None
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1) * 100)
    return round(-100 / (decimal_odds - 1))


class TheScoreAdapter(BookAdapter):
    name = "thescore"

    def supported_sports(self) -> list[Sport]:
        return list(_SPORT_PATHS.keys())

    def _fetch_raw(self, sport: Sport) -> dict | None:
        path = _SPORT_PATHS.get(sport)
        if path is None:
            return None
        url = f"{_BASE_URL}/sport/{path}/events"
        try:
            resp = cffi_requests.get(
                url,
                params={"limit": "200", "status": "pre"},
                impersonate="chrome120",
                headers={"Accept": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("TheScore fetch failed for %s: %s", sport, exc)
            return None

    def _parse_event_teams(self, event: dict) -> tuple[str, str] | None:
        """Extract (away, home) from event competitors or name."""
        competitors = event.get("competitors", [])
        if len(competitors) >= 2:
            away = home = None
            for comp in competitors:
                qualifier = comp.get("qualifier", "").lower()
                if qualifier == "home":
                    home = comp.get("name", "").strip()
                elif qualifier == "away":
                    away = comp.get("name", "").strip()
            if away and home:
                return away, home

        name = event.get("name", "")
        if " @ " in name:
            parts = name.split(" @ ", 1)
            return parts[0].strip(), parts[1].strip()
        if " vs " in name.lower():
            parts = name.split(" vs ", 1)
            return parts[0].strip(), parts[1].strip()
        return None

    def _find_market(self, markets: list[dict], market_name: str) -> dict | None:
        """Find a market by name."""
        for mkt in markets:
            name = mkt.get("name", "").lower()
            if market_name.lower() in name:
                return mkt
        return None

    def _extract_odds(self, selection: dict) -> int | None:
        """Extract American odds from a selection."""
        american = _parse_american(selection.get("americanOdds"))
        if american is not None:
            return american
        price = selection.get("price", {})
        american = _parse_american(price.get("american"))
        if american is not None:
            return american
        decimal_val = price.get("decimal") or selection.get("decimalOdds")
        if decimal_val:
            return _decimal_to_american(float(decimal_val))
        return None

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        now = datetime.now(timezone.utc).isoformat()
        events = data.get("events", data) if isinstance(data, dict) else data

        games: list[Game] = []
        for event in events if isinstance(events, list) else []:
            teams = self._parse_event_teams(event)
            if not teams:
                continue
            away_raw, home_raw = teams

            markets = event.get("markets", [])
            mkt = self._find_market(markets, "Moneyline")
            if not mkt:
                continue

            home_odds = away_odds = None
            for sel in mkt.get("selections", mkt.get("outcomes", [])):
                name = sel.get("name", sel.get("label", ""))
                odds_val = self._extract_odds(sel)
                if odds_val is None:
                    continue
                if name in home_raw or home_raw in name:
                    home_odds = odds_val
                elif name in away_raw or away_raw in name:
                    away_odds = odds_val

            if home_odds is None and away_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_raw,
                    away_team=away_raw,
                    start_time=event.get("startTime", event.get("start_time")),
                    game_id=str(event.get("id", "")),
                    lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
                )
            )

        logger.info("TheScore %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        now = datetime.now(timezone.utc).isoformat()
        market_name = "Run Line" if sport == Sport.MLB else "Spread"
        events = data.get("events", data) if isinstance(data, dict) else data

        games: list[Game] = []
        for event in events if isinstance(events, list) else []:
            teams = self._parse_event_teams(event)
            if not teams:
                continue
            away_raw, home_raw = teams

            markets = event.get("markets", [])
            mkt = self._find_market(markets, market_name)
            if not mkt:
                continue

            home_spread = away_spread = None
            home_spread_odds = away_spread_odds = None
            for sel in mkt.get("selections", mkt.get("outcomes", [])):
                name = sel.get("name", sel.get("label", ""))
                odds_val = self._extract_odds(sel)
                if odds_val is None:
                    continue
                handicap = sel.get("handicap") or sel.get("line") or sel.get("points")
                if name in home_raw or home_raw in name:
                    home_spread = handicap
                    home_spread_odds = odds_val
                elif name in away_raw or away_raw in name:
                    away_spread = handicap
                    away_spread_odds = odds_val

            if home_spread_odds is None and away_spread_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_raw,
                    away_team=away_raw,
                    start_time=event.get("startTime", event.get("start_time")),
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

        logger.info("TheScore %s spreads: %d games", sport.value, len(games))
        return games

    # -- Totals --

    def fetch_totals(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        now = datetime.now(timezone.utc).isoformat()
        events = data.get("events", data) if isinstance(data, dict) else data

        games: list[Game] = []
        for event in events if isinstance(events, list) else []:
            teams = self._parse_event_teams(event)
            if not teams:
                continue
            away_raw, home_raw = teams

            markets = event.get("markets", [])
            mkt = self._find_market(markets, "Total")
            if not mkt:
                continue

            total = None
            over_odds = under_odds = None
            for sel in mkt.get("selections", mkt.get("outcomes", [])):
                name = sel.get("name", sel.get("label", "")).lower()
                odds_val = self._extract_odds(sel)
                if odds_val is None:
                    continue
                handicap = sel.get("handicap") or sel.get("line") or sel.get("points")
                if "over" in name:
                    over_odds = odds_val
                    total = handicap
                elif "under" in name:
                    under_odds = odds_val
                    if total is None:
                        total = handicap

            if over_odds is None and under_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_raw,
                    away_team=away_raw,
                    start_time=event.get("startTime", event.get("start_time")),
                    game_id=str(event.get("id", "")),
                    lines=[
                        Line(book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now)
                    ],
                )
            )

        logger.info("TheScore %s totals: %d games", sport.value, len(games))
        return games
