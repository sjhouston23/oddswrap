"""BetRivers (Kambi) Sportsbook adapter.

BetRivers uses the Kambi platform. This adapter can also serve other
Kambi-backed books (Unibet, etc.) by changing the operator slug.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import (
    Game,
    Line,
    PlayerProp,
    PropCategory,
    Sport,
    decimal_to_american,
    normalize_start_time,
    parse_american,
)

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

_EVENT_URL = (
    "https://eu-offering-api.kambicdn.com/offering/v2018/{operator}/betoffer/event/{event_id}.json?lang=en_US&market=US"
)

# Kambi betOfferType names
_MONEYLINE_TYPES = {"TWO_WAY", "Match"}
_SPREAD_TYPES = {"TWO_WAY_HANDICAP", "Handicap"}
_TOTAL_TYPES = {"OVER_UNDER", "Over/Under"}

# Criterion labels for full-game markets only
_SPREAD_CRITERIA = {"Run Line", "Spread", "Puck Line"}
_TOTAL_CRITERIA = {"Total Runs", "Total Goals", "Total Points", "Total"}


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

    def _fetch_raw(self, sport: Sport) -> list[dict] | None:
        """Fetch raw event wrappers from Kambi API.

        Returns a list of wrappers, each with ``event`` and ``betOffers`` keys.
        """
        path = _SPORT_PATHS.get(sport)
        if path is None:
            return None
        url = _BASE_URL.format(operator=self._operator, path=path)
        try:
            resp = cffi_requests.get(url, impersonate="chrome120", timeout=15)
            resp.raise_for_status()
            return resp.json().get("events", [])
        except Exception as exc:
            logger.warning("BetRivers fetch failed for %s: %s", sport, exc)
            return None

    def _build_event_map(self, wrappers: list[dict]) -> dict[int, dict]:
        """Build {event_id: inner_event} map from response wrappers."""
        events = {}
        for wrapper in wrappers:
            ev = wrapper.get("event", {})
            eid = ev.get("id")
            home = ev.get("homeName")
            away = ev.get("awayName")
            if eid and home and away:
                events[eid] = ev
        return events

    def _get_bet_offers(
        self, wrappers: list[dict], offer_types: set[str], criteria: set[str] | None = None
    ) -> list[dict]:
        """Collect betOffers matching offer_types (and optionally criterion labels) from wrappers."""
        offers = []
        for wrapper in wrappers:
            for bo in wrapper.get("betOffers", []):
                type_name = bo.get("betOfferType", {}).get("name", "")
                if type_name not in offer_types:
                    continue
                if criteria is not None:
                    crit_label = bo.get("criterion", {}).get("label", "")
                    if crit_label not in criteria:
                        continue
                offers.append(bo)
        return offers

    def _fetch_event_offers(self, event_ids: list[int]) -> list[dict]:
        """Fetch full betOffers for a list of event IDs (per-event endpoint).

        Returns a flat list of betOffer dicts with eventId populated.
        """
        all_offers = []
        for eid in event_ids:
            url = _EVENT_URL.format(operator=self._operator, event_id=eid)
            try:
                resp = cffi_requests.get(url, impersonate="chrome120", timeout=15)
                resp.raise_for_status()
                data = resp.json()
                all_offers.extend(data.get("betOffers", []))
            except Exception as exc:
                logger.warning("BetRivers event %s fetch failed: %s", eid, exc)
        return all_offers

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
                    start_time=normalize_start_time(ev.get("start")),
                    game_id=str(eid),
                    live=ev.get("state") != "NOT_STARTED",
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
        # listView may not include spread offers; fetch per-event
        spread_offers = self._get_bet_offers(data, _SPREAD_TYPES, _SPREAD_CRITERIA)
        if not spread_offers:
            all_offers = self._fetch_event_offers(list(events.keys()))
            spread_offers = [
                bo
                for bo in all_offers
                if bo.get("betOfferType", {}).get("name", "") in _SPREAD_TYPES
                and bo.get("criterion", {}).get("label", "") in _SPREAD_CRITERIA
                and "MAIN_LINE" in bo.get("tags", [])
            ]
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
                    start_time=normalize_start_time(ev.get("start")),
                    game_id=str(eid),
                    live=ev.get("state") != "NOT_STARTED",
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
        # listView may not include total offers; fetch per-event
        total_offers = self._get_bet_offers(data, _TOTAL_TYPES, _TOTAL_CRITERIA)
        if not total_offers:
            all_offers = self._fetch_event_offers(list(events.keys()))
            total_offers = [
                bo
                for bo in all_offers
                if bo.get("betOfferType", {}).get("name", "") in _TOTAL_TYPES
                and bo.get("criterion", {}).get("label", "") in _TOTAL_CRITERIA
                and "MAIN_LINE" in bo.get("tags", [])
            ]
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
                    start_time=normalize_start_time(ev.get("start")),
                    game_id=str(eid),
                    live=ev.get("state") != "NOT_STARTED",
                    lines=[
                        Line(book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now)
                    ],
                )
            )

        logger.info("BetRivers %s totals: %d games", sport.value, len(games))
        return games

    # -- Player Props --

    def fetch_prop_categories(self, sport: Sport) -> list[PropCategory]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        events = self._build_event_map(data)
        if not events:
            return []

        # Fetch one event's full offers to discover available criterion labels
        sample_eid = next(iter(events))
        all_offers = self._fetch_event_offers([sample_eid])

        seen: set[tuple[str, str]] = set()
        results: list[PropCategory] = []
        for bo in all_offers:
            bt = bo.get("betOfferType", {}).get("name", "")
            crit = bo.get("criterion", {}).get("label", "")
            if not crit or (bt, crit) in seen:
                continue
            seen.add((bt, crit))
            results.append(
                PropCategory(
                    book=self.name,
                    category_id=bt,
                    category_name=bt,
                    subcategory_id=crit,
                    subcategory_name=crit,
                )
            )

        return results

    def fetch_props(self, sport: Sport, category_id: str, subcategory_id: str | None = None) -> list[PlayerProp]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        events = self._build_event_map(data)
        if not events:
            return []

        all_offers = self._fetch_event_offers(list(events.keys()))
        now = datetime.now(timezone.utc).isoformat()

        props: list[PlayerProp] = []
        for bo in all_offers:
            bt = bo.get("betOfferType", {}).get("name", "")
            crit = bo.get("criterion", {}).get("label", "")

            if bt != category_id:
                continue
            if subcategory_id and crit != subcategory_id:
                continue

            eid = bo.get("eventId")
            ev = events.get(eid, {})
            game_name = f"{ev.get('awayName', '?')} @ {ev.get('homeName', '?')}" if ev else None

            outcomes = bo.get("outcomes", [])
            over_odds = under_odds = None
            line = None
            player = None

            for o in outcomes:
                label = o.get("label", "")
                otype = o.get("type", "")
                val = _kambi_odds_to_american(o)
                handicap = _kambi_line(o.get("line"))

                # Player name from 'participant' field (Kambi player props)
                if o.get("participant") and player is None:
                    player = o["participant"]

                if "over" in label.lower() or otype == "OT_OVER":
                    over_odds = val
                    if handicap is not None:
                        line = handicap
                elif "under" in label.lower() or otype == "OT_UNDER":
                    under_odds = val
                    if line is None and handicap is not None:
                        line = handicap
                elif player is None:
                    player = label

            if over_odds is None and under_odds is None:
                continue

            props.append(
                PlayerProp(
                    book=self.name,
                    player=player or crit,
                    market=crit,
                    line=line,
                    over_odds=over_odds,
                    under_odds=under_odds,
                    game=game_name,
                    event_id=str(eid) if eid else None,
                    fetched_at=now,
                )
            )

        logger.info("BetRivers %s props: %d", sport.value, len(props))
        return props
