"""BetMGM Sportsbook adapter (bwin/Entain CDS API)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, Sport, decimal_to_american, parse_american

logger = logging.getLogger("oddswrap.betmgm")

# BetMGM sport IDs and competition IDs per sport
_SPORT_IDS: dict[Sport, str] = {
    Sport.MLB: "23",
    Sport.NBA: "7",
    Sport.NFL: "11",
    Sport.NHL: "12",
}

_COMPETITION_IDS: dict[Sport, str] = {
    Sport.MLB: "75",
    Sport.NBA: "6004",
    Sport.NFL: "35",
    Sport.NHL: "25",
}

_BASE_URL = "https://sports.{state}.betmgm.com/cds-api/bettingoffer/fixtures"
_ACCESS_ID = "OTU4NDk3MzEtOTAyNS00MjQzLWIxNWEtNTI2MjdhNWM3Zjk3"

# Market name mappings
_MONEYLINE_NAMES = {"Moneyline", "Money Line"}
_SPREAD_NAMES = {"Run Line", "Point Spread", "Spread", "Puck Line"}
_TOTAL_NAMES = {"Total Runs", "Total Points", "Total Goals", "Total", "Over/Under"}


def _parse_result_odds(result: dict) -> int | None:
    """Extract American odds from a BetMGM result.

    Uses americanOdds string if available, falls back to decimal conversion.
    """
    american_str = result.get("americanOdds")
    if american_str is not None:
        val = parse_american(american_str)
        if val is not None:
            return val
    # Fall back to decimal odds
    dec = result.get("odds")
    if dec is None:
        return None
    try:
        return decimal_to_american(float(dec))
    except (ValueError, TypeError):
        return None


def _parse_handicap(val) -> float | None:
    """Parse handicap/attr value."""
    if val is None:
        return None
    try:
        return float(str(val))
    except (ValueError, TypeError):
        return None


class BetMGMAdapter(BookAdapter):
    name = "betmgm"

    def __init__(self, state: str = "nj"):
        self._state = state

    def supported_sports(self) -> list[Sport]:
        return list(_COMPETITION_IDS.keys())

    def _fetch_raw(self, sport: Sport) -> list[dict] | None:
        comp_id = _COMPETITION_IDS.get(sport)
        sport_id = _SPORT_IDS.get(sport)
        if comp_id is None or sport_id is None:
            return None
        url = _BASE_URL.format(state=self._state)
        try:
            resp = cffi_requests.get(
                url,
                params={
                    "x-bwin-accessid": _ACCESS_ID,
                    "lang": "en-us",
                    "country": "US",
                    "userCountry": "US",
                    "offerMapping": "Filtered",
                    "sportIds": sport_id,
                    "competitionIds": comp_id,
                    "fixtureTypes": "Standard",
                    "offerCategories": "Gridable",
                },
                impersonate="chrome120",
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("fixtures", [])
        except Exception as exc:
            logger.warning("BetMGM fetch failed for %s: %s", sport, exc)
            return None

    def _get_teams(self, fixture: dict) -> tuple[str, str] | None:
        """Extract (away_team, home_team) from participants."""
        home = away = None
        for p in fixture.get("participants", []):
            ptype = p.get("properties", {}).get("type", "").upper()
            name = p.get("name", {}).get("value", "")
            if not name:
                continue
            if ptype == "HOME":
                home = name
            elif ptype == "AWAY":
                away = name
        if home and away:
            return away, home
        return None

    def _get_markets(self, fixture: dict, market_names: set[str]) -> list[dict]:
        """Filter games (markets) by name within a fixture."""
        markets = []
        for game in fixture.get("games", []):
            if game.get("visibility") != "Visible":
                continue
            name = game.get("name", {}).get("value", "")
            if name in market_names:
                markets.append(game)
        return markets

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        fixtures = self._fetch_raw(sport)
        if not fixtures:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for fix in fixtures:
            teams = self._get_teams(fix)
            if not teams:
                continue
            away_name, home_name = teams

            for mkt in self._get_markets(fix, _MONEYLINE_NAMES):
                home_odds = away_odds = None
                for result in mkt.get("results", []):
                    if result.get("visibility") != "Visible":
                        continue
                    name = result.get("name", {}).get("value", "")
                    val = _parse_result_odds(result)
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
                        start_time=fix.get("startDate"),
                        game_id=str(fix.get("id", "")),
                        lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
                    )
                )

        logger.info("BetMGM %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        fixtures = self._fetch_raw(sport)
        if not fixtures:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for fix in fixtures:
            teams = self._get_teams(fix)
            if not teams:
                continue
            away_name, home_name = teams

            for mkt in self._get_markets(fix, _SPREAD_NAMES):
                home_spread = away_spread = None
                home_spread_odds = away_spread_odds = None
                for result in mkt.get("results", []):
                    if result.get("visibility") != "Visible":
                        continue
                    name = result.get("name", {}).get("value", "")
                    val = _parse_result_odds(result)
                    handicap = _parse_handicap(result.get("attr"))
                    if val is None:
                        continue
                    if name == home_name or home_name in name or name in home_name:
                        home_spread = handicap
                        home_spread_odds = val
                    elif name == away_name or away_name in name or name in away_name:
                        away_spread = handicap
                        away_spread_odds = val

                if home_spread_odds is None and away_spread_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_name,
                        away_team=away_name,
                        start_time=fix.get("startDate"),
                        game_id=str(fix.get("id", "")),
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
        fixtures = self._fetch_raw(sport)
        if not fixtures:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for fix in fixtures:
            teams = self._get_teams(fix)
            if not teams:
                continue
            away_name, home_name = teams

            for mkt in self._get_markets(fix, _TOTAL_NAMES):
                total = None
                over_odds = under_odds = None
                for result in mkt.get("results", []):
                    if result.get("visibility") != "Visible":
                        continue
                    name = result.get("name", {}).get("value", "").lower()
                    val = _parse_result_odds(result)
                    handicap = _parse_handicap(result.get("attr"))
                    if val is None:
                        continue
                    if "over" in name:
                        over_odds = val
                        total = handicap
                    elif "under" in name:
                        under_odds = val
                        if total is None:
                            total = handicap

                if over_odds is None and under_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_name,
                        away_team=away_name,
                        start_time=fix.get("startDate"),
                        game_id=str(fix.get("id", "")),
                        lines=[
                            Line(
                                book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now
                            )
                        ],
                    )
                )

        logger.info("BetMGM %s totals: %d games", sport.value, len(games))
        return games
