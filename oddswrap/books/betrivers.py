"""BetRivers Sportsbook adapter (powered by Kambi)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, Sport

logger = logging.getLogger("oddswrap.betrivers")

# Kambi sport group and league path per sport
_SPORT_PATHS: dict[Sport, str] = {
    Sport.MLB: "baseball/mlb",
    Sport.NBA: "basketball/nba",
    Sport.NFL: "american_football/nfl",
    Sport.NHL: "ice_hockey/nhl",
}

# Kambi betOfferType IDs
_MONEYLINE_TYPE = 2  # "Match"
_HANDICAP_TYPE = 1  # "Handicap" (spread / run line / puck line)
_OVER_UNDER_TYPE = 6  # "Over/Under" (totals)

_BASE_URL = "https://eu-offering-api.kambicdn.com/offering/v2018/rsiuspa"


def _parse_american(val) -> int | None:
    if val is None:
        return None
    try:
        return int(str(val).replace("\u2212", "-").replace("+", ""))
    except (ValueError, TypeError):
        return None


class BetRiversAdapter(BookAdapter):
    name = "betrivers"

    def supported_sports(self) -> list[Sport]:
        return list(_SPORT_PATHS.keys())

    def _fetch_events(self, sport: Sport) -> list[dict] | None:
        """Fetch event list with embedded main betOffers from Kambi listView."""
        path = _SPORT_PATHS.get(sport)
        if path is None:
            return None
        url = f"{_BASE_URL}/listView/{path}.json"
        try:
            resp = cffi_requests.get(
                url,
                params={"lang": "en_US", "market": "US"},
                impersonate="chrome120",
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("events", [])
        except Exception as exc:
            logger.warning("BetRivers listView failed for %s: %s", sport, exc)
            return None

    def _fetch_event_offers(self, event_id: int) -> list[dict] | None:
        """Fetch all betOffers for a single event."""
        url = f"{_BASE_URL}/betoffer/event/{event_id}.json"
        try:
            resp = cffi_requests.get(
                url,
                params={"lang": "en_US", "market": "US", "includeParticipants": "true"},
                impersonate="chrome120",
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("betOffers", [])
        except Exception as exc:
            logger.warning("BetRivers betoffer fetch failed for event %s: %s", event_id, exc)
            return None

    def _parse_event_teams(self, ev: dict) -> tuple[str, str] | None:
        home = ev.get("homeName", "").strip()
        away = ev.get("awayName", "").strip()
        if not home or not away:
            return None
        return away, home

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        events = self._fetch_events(sport)
        if not events:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for ev in events:
            teams = self._parse_event_teams(ev)
            if not teams:
                continue
            away_raw, home_raw = teams

            for bo in ev.get("betOffers", []):
                if bo.get("betOfferType", {}).get("id") != _MONEYLINE_TYPE:
                    continue

                home_odds = away_odds = None
                for oc in bo.get("outcomes", []):
                    val = _parse_american(oc.get("oddsAmerican"))
                    if val is None:
                        continue
                    label = oc.get("label", "")
                    if label in home_raw or home_raw in label:
                        home_odds = val
                    elif label in away_raw or away_raw in label:
                        away_odds = val

                if home_odds is None and away_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_raw,
                        away_team=away_raw,
                        start_time=ev.get("start"),
                        game_id=str(ev.get("id", "")),
                        lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
                    )
                )
                break  # Only take the first moneyline offer per event

        logger.info("BetRivers %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        events = self._fetch_events(sport)
        if not events:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for ev in events:
            teams = self._parse_event_teams(ev)
            if not teams:
                continue
            away_raw, home_raw = teams

            offers = self._fetch_event_offers(ev.get("id"))
            if not offers:
                continue

            for bo in offers:
                if bo.get("betOfferType", {}).get("id") != _HANDICAP_TYPE:
                    continue
                criterion = bo.get("criterion", {}).get("label", "").lower()
                if "run line" not in criterion and "spread" not in criterion and "puck line" not in criterion:
                    continue

                home_spread = away_spread = None
                home_spread_odds = away_spread_odds = None
                for oc in bo.get("outcomes", []):
                    val = _parse_american(oc.get("oddsAmerican"))
                    line = oc.get("line")
                    if val is None:
                        continue
                    label = oc.get("label", "")
                    if label in home_raw or home_raw in label:
                        home_spread = line / 1000 if line is not None else None
                        home_spread_odds = val
                    elif label in away_raw or away_raw in label:
                        away_spread = line / 1000 if line is not None else None
                        away_spread_odds = val

                if home_spread_odds is None and away_spread_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_raw,
                        away_team=away_raw,
                        start_time=ev.get("start"),
                        game_id=str(ev.get("id", "")),
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
                break  # Only take the first spread offer per event

        logger.info("BetRivers %s spreads: %d games", sport.value, len(games))
        return games

    # -- Totals --

    def fetch_totals(self, sport: Sport) -> list[Game]:
        events = self._fetch_events(sport)
        if not events:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for ev in events:
            teams = self._parse_event_teams(ev)
            if not teams:
                continue
            away_raw, home_raw = teams

            offers = self._fetch_event_offers(ev.get("id"))
            if not offers:
                continue

            for bo in offers:
                if bo.get("betOfferType", {}).get("id") != _OVER_UNDER_TYPE:
                    continue
                criterion = bo.get("criterion", {}).get("label", "").lower()
                if "total" not in criterion:
                    continue

                total = None
                over_odds = under_odds = None
                for oc in bo.get("outcomes", []):
                    label = oc.get("label", "").lower()
                    val = _parse_american(oc.get("oddsAmerican"))
                    line = oc.get("line")
                    if val is None:
                        continue
                    if "over" in label:
                        over_odds = val
                        total = line / 1000 if line is not None else None
                    elif "under" in label:
                        under_odds = val
                        if total is None and line is not None:
                            total = line / 1000

                if over_odds is None and under_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_raw,
                        away_team=away_raw,
                        start_time=ev.get("start"),
                        game_id=str(ev.get("id", "")),
                        lines=[
                            Line(
                                book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now
                            )
                        ],
                    )
                )
                break  # Only take the first total offer per event

        logger.info("BetRivers %s totals: %d games", sport.value, len(games))
        return games
