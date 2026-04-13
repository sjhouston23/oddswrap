"""BetRivers (Kambi) Sportsbook adapter.

BetRivers uses the Kambi platform. This adapter can also serve other
Kambi-backed books (Unibet, etc.) by changing the operator slug.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, Sport, decimal_to_american, parse_american

logger = logging.getLogger("oddswrap.betrivers")

# Kambi sport/league paths per Sport enum
_SPORT_PATHS: dict[Sport, str] = {
    Sport.MLB: "baseball/mlb",
    Sport.NBA: "basketball/nba",
    Sport.NFL: "american_football/nfl",
    Sport.NHL: "ice_hockey/nhl",
}

_BASE_URL = (
    "https://eu-offering-api.kambicdn.com/offering/v2018/{operator}"
    "/listView/{path}/all/all/matches.json?lang=en_US&market=US"
)

# Kambi betOfferType names (numeric IDs: 2=TWO_WAY, 1=TWO_WAY_HANDICAP, 6=OVER_UNDER)
_MONEYLINE_TYPES = {"TWO_WAY", "Match"}
_SPREAD_TYPES = {"TWO_WAY_HANDICAP", "Handicap"}
_TOTAL_TYPES = {"OVER_UNDER", "Over/Under"}


def _kambi_odds_to_american(outcome: dict) -> int | None:
    """Extract American odds from a Kambi outcome.

    Uses oddsAmerican string if available, falls back to decimal conversion.
    """
    # Try pre-formatted American odds first
    american_str = outcome.get("oddsAmerican")
    if american_str is not None:
        val = parse_american(american_str)
        if val is not None:
            return val
    # Fall back to decimal * 1000 conversion
    odds = outcome.get("odds")
    if odds is None or odds <= 1000:
        return None
    return decimal_to_american(odds / 1000)


def _kambi_line(line: int | None) -> float | None:
    """Convert Kambi line (value * 1000) to float."""
    if line is None:
        return None
    return line / 1000


class BetRiversAdapter(BookAdapter):
    name = "betrivers"

    def __init__(self, operator: str = "rsiusnj", display_name: str | None = None):
        self._operator = operator
        if display_name:
            self.name = display_name

    def supported_sports(self) -> list[Sport]:
        return list(_SPORT_PATHS.keys())

    def _fetch_raw(self, sport: Sport) -> dict | None:
        path = _SPORT_PATHS.get(sport)
        if path is None:
            return None
        url = _BASE_URL.format(operator=self._operator, path=path)
        try:
            resp = cffi_requests.get(url, impersonate="chrome120", timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("BetRivers fetch failed for %s: %s", sport, exc)
            return None

    def _build_event_map(self, data: dict) -> dict[int, dict]:
        """Build {event_id: event} map from response."""
        events = {}
        for ev in data.get("events", []):
            eid = ev.get("id")
            home = ev.get("homeName")
            away = ev.get("awayName")
            if eid and home and away:
                events[eid] = ev
        return events

    def _get_bet_offers(self, data: dict, offer_types: set[str]) -> list[dict]:
        """Filter betOffers by betOfferType name."""
        offers = []
        for bo in data.get("betOffers", []):
            type_name = bo.get("betOfferType", {}).get("name", "")
            if type_name in offer_types:
                offers.append(bo)
        return offers

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        events = self._build_event_map(data)
        ml_offers = self._get_bet_offers(data, _MONEYLINE_TYPES)
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for bo in ml_offers:
            eid = bo.get("eventId")
            ev = events.get(eid)
            if not ev:
                continue
            home_name = ev["homeName"]
            away_name = ev["awayName"]

            home_odds = away_odds = None
            for outcome in bo.get("outcomes", []):
                if outcome.get("status") != "OPEN":
                    continue
                label = outcome.get("label", "")
                val = _kambi_odds_to_american(outcome)
                if val is None:
                    continue
                if label == home_name:
                    home_odds = val
                elif label == away_name:
                    away_odds = val

            if home_odds is None and away_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_name,
                    away_team=away_name,
                    start_time=ev.get("start"),
                    game_id=str(eid),
                    lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
                )
            )

        logger.info("BetRivers %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        events = self._build_event_map(data)
        spread_offers = self._get_bet_offers(data, _SPREAD_TYPES)
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for bo in spread_offers:
            eid = bo.get("eventId")
            ev = events.get(eid)
            if not ev:
                continue
            home_name = ev["homeName"]
            away_name = ev["awayName"]

            home_spread = away_spread = None
            home_spread_odds = away_spread_odds = None
            for outcome in bo.get("outcomes", []):
                if outcome.get("status") != "OPEN":
                    continue
                label = outcome.get("label", "")
                val = _kambi_odds_to_american(outcome)
                handicap = _kambi_line(outcome.get("line"))
                if val is None:
                    continue
                if label == home_name:
                    home_spread = handicap
                    home_spread_odds = val
                elif label == away_name:
                    away_spread = handicap
                    away_spread_odds = val

            if home_spread_odds is None and away_spread_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_name,
                    away_team=away_name,
                    start_time=ev.get("start"),
                    game_id=str(eid),
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

        logger.info("BetRivers %s spreads: %d games", sport.value, len(games))
        return games

    # -- Totals --

    def fetch_totals(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        events = self._build_event_map(data)
        total_offers = self._get_bet_offers(data, _TOTAL_TYPES)
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for bo in total_offers:
            eid = bo.get("eventId")
            ev = events.get(eid)
            if not ev:
                continue
            home_name = ev["homeName"]
            away_name = ev["awayName"]

            total = None
            over_odds = under_odds = None
            for outcome in bo.get("outcomes", []):
                if outcome.get("status") != "OPEN":
                    continue
                label = outcome.get("label", "").lower()
                otype = outcome.get("type", "")
                val = _kambi_odds_to_american(outcome)
                handicap = _kambi_line(outcome.get("line"))
                if val is None:
                    continue
                if "over" in label or otype == "OT_OVER":
                    over_odds = val
                    total = handicap
                elif "under" in label or otype == "OT_UNDER":
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
                    start_time=ev.get("start"),
                    game_id=str(eid),
                    lines=[
                        Line(book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now)
                    ],
                )
            )

        logger.info("BetRivers %s totals: %d games", sport.value, len(games))
        return games
