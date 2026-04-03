"""BetMGM Sportsbook adapter (powered by bwin/Entain platform)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, Sport

logger = logging.getLogger("oddswrap.betmgm")

# bwin CDS API — sportIds per sport
_SPORT_IDS: dict[Sport, int] = {
    Sport.MLB: 23,
    Sport.NBA: 7,
    Sport.NFL: 11,
    Sport.NHL: 12,
}

_BASE_URL = "https://sports.nj.betmgm.com/cds-api/bettingoffer/fixtures"
_ACCESS_ID = "OTU4NDk3MzEtOTAyNS00MjQzLWIxNWEtNTI2MjdhNWM3Zjk3"


def _parse_american(val) -> int | None:
    if val is None:
        return None
    try:
        return int(str(val).replace("\u2212", "-"))
    except (ValueError, TypeError):
        return None


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).replace("\u2212", "-"))
    except (ValueError, TypeError):
        return None


def _odds_to_american(decimal_odds: float) -> int | None:
    """Convert European decimal odds to American format."""
    if decimal_odds is None or decimal_odds <= 1.0:
        return None
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1) * 100)
    return round(-100 / (decimal_odds - 1))


class BetMGMAdapter(BookAdapter):
    name = "betmgm"

    def supported_sports(self) -> list[Sport]:
        return list(_SPORT_IDS.keys())

    def _fetch_raw(self, sport: Sport) -> dict | None:
        sport_id = _SPORT_IDS.get(sport)
        if sport_id is None:
            return None
        try:
            resp = cffi_requests.get(
                _BASE_URL,
                params={
                    "x-bwin-accessid": _ACCESS_ID,
                    "lang": "en-us",
                    "country": "US",
                    "userCountry": "US",
                    "fixtureTypes": "Standard",
                    "state": "Latest",
                    "offerMapping": "Filtered",
                    "offerCategories": "Gridable",
                    "fixtureCategories": "Gridable,Scoreboard",
                    "sportIds": str(sport_id),
                    "skip": "0",
                    "take": "200",
                    "sortBy": "Tags",
                },
                impersonate="chrome120",
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("BetMGM fetch failed for %s: %s", sport, exc)
            return None

    def _parse_fixture_teams(self, fixture: dict) -> tuple[str, str] | None:
        """Extract (away, home) team names from fixture participants."""
        participants = fixture.get("participants", [])
        if len(participants) < 2:
            return None
        # BetMGM lists away first, home second in standard fixture views
        away = participants[0].get("name", {}).get("value", "").strip()
        home = participants[1].get("name", {}).get("value", "").strip()
        if not away or not home:
            return None
        return away, home

    def _find_game(self, fixture: dict, market_name: str) -> dict | None:
        """Find a specific game (market) by name within a fixture."""
        for game in fixture.get("games", []):
            name = game.get("name", {}).get("value", "").lower()
            if market_name.lower() in name and game.get("visibility") == "Visible":
                return game
        return None

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for fixture in data.get("fixtures", []):
            teams = self._parse_fixture_teams(fixture)
            if not teams:
                continue
            away_raw, home_raw = teams

            game_data = self._find_game(fixture, "Moneyline")
            if not game_data:
                continue

            home_odds = away_odds = None
            for result in game_data.get("results", []):
                name = result.get("name", {}).get("value", "")
                odds_val = result.get("americanOdds")
                if odds_val is None:
                    decimal_val = result.get("odds")
                    odds_val = _odds_to_american(decimal_val) if decimal_val else None
                else:
                    odds_val = _parse_american(odds_val)
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
                    start_time=fixture.get("startDate"),
                    game_id=str(fixture.get("id", "")),
                    lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
                )
            )

        logger.info("BetMGM %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        now = datetime.now(timezone.utc).isoformat()
        market_name = "Run Line" if sport == Sport.MLB else "Spread"

        games: list[Game] = []
        for fixture in data.get("fixtures", []):
            teams = self._parse_fixture_teams(fixture)
            if not teams:
                continue
            away_raw, home_raw = teams

            game_data = self._find_game(fixture, market_name)
            if not game_data:
                continue

            home_spread = away_spread = None
            home_spread_odds = away_spread_odds = None
            for result in game_data.get("results", []):
                name = result.get("name", {}).get("value", "")
                odds_val = result.get("americanOdds")
                if odds_val is None:
                    decimal_val = result.get("odds")
                    odds_val = _odds_to_american(decimal_val) if decimal_val else None
                else:
                    odds_val = _parse_american(odds_val)
                attr = result.get("attr")
                if odds_val is None:
                    continue
                spread_val = _parse_float(attr)
                if name in home_raw or home_raw in name:
                    home_spread = spread_val
                    home_spread_odds = odds_val
                elif name in away_raw or away_raw in name:
                    away_spread = spread_val
                    away_spread_odds = odds_val

            if home_spread_odds is None and away_spread_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_raw,
                    away_team=away_raw,
                    start_time=fixture.get("startDate"),
                    game_id=str(fixture.get("id", "")),
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

        logger.info("BetMGM %s spreads: %d games", sport.value, len(games))
        return games

    # -- Totals --

    def fetch_totals(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for fixture in data.get("fixtures", []):
            teams = self._parse_fixture_teams(fixture)
            if not teams:
                continue
            away_raw, home_raw = teams

            game_data = self._find_game(fixture, "Total")
            if not game_data:
                continue

            total = None
            over_odds = under_odds = None
            for result in game_data.get("results", []):
                name = result.get("name", {}).get("value", "").lower()
                odds_val = result.get("americanOdds")
                if odds_val is None:
                    decimal_val = result.get("odds")
                    odds_val = _odds_to_american(decimal_val) if decimal_val else None
                else:
                    odds_val = _parse_american(odds_val)
                attr = result.get("attr")
                if odds_val is None:
                    continue
                total_val = _parse_float(attr)
                if "over" in name:
                    over_odds = odds_val
                    total = total_val
                elif "under" in name:
                    under_odds = odds_val
                    if total is None:
                        total = total_val

            if over_odds is None and under_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_raw,
                    away_team=away_raw,
                    start_time=fixture.get("startDate"),
                    game_id=str(fixture.get("id", "")),
                    lines=[
                        Line(book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now)
                    ],
                )
            )

        logger.info("BetMGM %s totals: %d games", sport.value, len(games))
        return games
