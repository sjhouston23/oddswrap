"""Caesars Sportsbook adapter (American Wagering / William Hill platform)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, Sport

logger = logging.getLogger("oddswrap.caesars")

# Caesars sport slugs
_SPORT_SLUGS: dict[Sport, str] = {
    Sport.MLB: "baseball",
    Sport.NBA: "basketball",
    Sport.NFL: "americanfootball",
    Sport.NHL: "icehockey",
}

# Competition IDs for major leagues
_COMPETITION_IDS: dict[Sport, str] = {
    Sport.MLB: "04f90892-3afa-4e84-acce-5b89f151063d",
    Sport.NBA: "5806c896-4eec-4de1-874f-a175fc0f40e3",
    Sport.NFL: "007d7c61-07a7-4e18-bb40-15104b6eac92",
    Sport.NHL: "b7b715a1-1571-42bb-bbd7-f22b77e90399",
}

_BASE_URL = "https://api.americanwagering.com/regions/us/locations/nj/brands/czr/sb/v3"


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


class CaesarsAdapter(BookAdapter):
    name = "caesars"

    def supported_sports(self) -> list[Sport]:
        return list(_SPORT_SLUGS.keys())

    def _fetch_raw(self, sport: Sport) -> dict | None:
        slug = _SPORT_SLUGS.get(sport)
        comp_id = _COMPETITION_IDS.get(sport)
        if slug is None:
            return None
        url = (
            f"{_BASE_URL}/sports/{slug}/events/competition/{comp_id}"
            if comp_id
            else f"{_BASE_URL}/sports/{slug}/events"
        )
        try:
            resp = cffi_requests.get(
                url,
                params={"limit": "200"},
                impersonate="chrome120",
                headers={"Accept": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Caesars fetch failed for %s: %s", sport, exc)
            return None

    def _parse_event_teams(self, event: dict) -> tuple[str, str] | None:
        """Extract (away, home) from event name or competitors."""
        competitors = event.get("competitors", [])
        if len(competitors) >= 2:
            away = home = None
            for comp in competitors:
                if comp.get("type", "").lower() == "home":
                    home = comp.get("name", "").strip()
                elif comp.get("type", "").lower() == "away":
                    away = comp.get("name", "").strip()
            if away and home:
                return away, home

        name = event.get("name", "")
        if " @ " in name:
            parts = name.split(" @ ", 1)
            return parts[0].strip(), parts[1].strip()
        if " vs " in name.lower():
            parts = name.lower().split(" vs ", 1)
            return parts[0].strip(), parts[1].strip()
        return None

    def _find_market(self, markets: list[dict], market_name: str) -> dict | None:
        """Find a market by name."""
        for mkt in markets:
            name = mkt.get("name", "").lower()
            if not mkt.get("active", True) or not mkt.get("display", True):
                continue
            if market_name.lower() in name:
                return mkt
        return None

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        now = datetime.now(timezone.utc).isoformat()
        events = (
            data.get("competitions", [{}])[0].get("events", []) if data.get("competitions") else data.get("events", [])
        )

        games: list[Game] = []
        for event in events:
            teams = self._parse_event_teams(event)
            if not teams:
                continue
            away_raw, home_raw = teams

            markets = event.get("markets", [])
            mkt = self._find_market(markets, "Moneyline")
            if not mkt:
                continue

            home_odds = away_odds = None
            for sel in mkt.get("selections", []):
                name = sel.get("name", "")
                price = sel.get("price", {})
                american = _parse_american(price.get("a"))
                if american is None:
                    decimal_val = price.get("d")
                    american = _decimal_to_american(decimal_val) if decimal_val else None
                if american is None:
                    continue
                if name in home_raw or home_raw in name:
                    home_odds = american
                elif name in away_raw or away_raw in name:
                    away_odds = american

            if home_odds is None and away_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_raw,
                    away_team=away_raw,
                    start_time=event.get("startTime"),
                    game_id=str(event.get("id", "")),
                    lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
                )
            )

        logger.info("Caesars %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        now = datetime.now(timezone.utc).isoformat()
        market_name = "Run Line" if sport == Sport.MLB else "Spread"
        events = (
            data.get("competitions", [{}])[0].get("events", []) if data.get("competitions") else data.get("events", [])
        )

        games: list[Game] = []
        for event in events:
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
            line_val = mkt.get("line")
            for sel in mkt.get("selections", []):
                name = sel.get("name", "")
                price = sel.get("price", {})
                american = _parse_american(price.get("a"))
                if american is None:
                    decimal_val = price.get("d")
                    american = _decimal_to_american(decimal_val) if decimal_val else None
                if american is None:
                    continue
                handicap = sel.get("price", {}).get("handicap") or sel.get("handicap") or line_val
                if name in home_raw or home_raw in name:
                    home_spread = handicap
                    home_spread_odds = american
                elif name in away_raw or away_raw in name:
                    away_spread = handicap
                    away_spread_odds = american

            if home_spread_odds is None and away_spread_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_raw,
                    away_team=away_raw,
                    start_time=event.get("startTime"),
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
        data = self._fetch_raw(sport)
        if not data:
            return []
        now = datetime.now(timezone.utc).isoformat()
        events = (
            data.get("competitions", [{}])[0].get("events", []) if data.get("competitions") else data.get("events", [])
        )

        games: list[Game] = []
        for event in events:
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
            line_val = mkt.get("line")
            for sel in mkt.get("selections", []):
                name = sel.get("name", "").lower()
                price = sel.get("price", {})
                american = _parse_american(price.get("a"))
                if american is None:
                    decimal_val = price.get("d")
                    american = _decimal_to_american(decimal_val) if decimal_val else None
                if american is None:
                    continue
                handicap = sel.get("price", {}).get("handicap") or sel.get("handicap") or line_val
                if "over" in name:
                    over_odds = american
                    total = handicap
                elif "under" in name:
                    under_odds = american
                    if total is None:
                        total = handicap

            if over_odds is None and under_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_raw,
                    away_team=away_raw,
                    start_time=event.get("startTime"),
                    game_id=str(event.get("id", "")),
                    lines=[
                        Line(book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now)
                    ],
                )
            )

        logger.info("Caesars %s totals: %d games", sport.value, len(games))
        return games
