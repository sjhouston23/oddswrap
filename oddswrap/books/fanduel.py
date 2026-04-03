"""FanDuel Sportsbook adapter."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, Sport

logger = logging.getLogger("oddswrap.fanduel")

# FanDuel sbapi — customPageId per sport
_PAGE_IDS: Dict[Sport, str] = {
    Sport.MLB: "mlb",
    Sport.NBA: "nba",
    Sport.NFL: "nfl",
    Sport.NHL: "nhl",
}

_BASE_URL = "https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"
_API_KEY = "FhMFpcPWXMeyZxOx"


def _parse_american(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(str(val).replace("\u2212", "-"))
    except (ValueError, TypeError):
        return None


class FanDuelAdapter(BookAdapter):
    name = "fanduel"

    def supported_sports(self) -> List[Sport]:
        return list(_PAGE_IDS.keys())

    def _fetch_raw(self, sport: Sport) -> Optional[dict]:
        page_id = _PAGE_IDS.get(sport)
        if page_id is None:
            return None
        try:
            resp = cffi_requests.get(
                _BASE_URL,
                params={"page": "CUSTOM", "customPageId": page_id, "_ak": _API_KEY},
                impersonate="chrome120",
                headers={"Accept": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("FanDuel fetch failed for %s: %s", sport, exc)
            return None

    def _parse_game_events(self, data: dict) -> Dict[str, dict]:
        events = data.get("attachments", {}).get("events", {})
        return {str(eid): ev for eid, ev in events.items() if " @ " in ev.get("name", "")}

    def _parse_event_teams(self, ev: dict) -> Optional[Tuple[str, str]]:
        name = ev.get("name", "")
        parts = name.split(" @ ", 1)
        if len(parts) != 2:
            return None
        away = parts[0].strip().split(" (")[0].strip()
        home = parts[1].strip().split(" (")[0].strip()
        return away, home

    def _get_markets(self, data: dict, market_name: str) -> List[dict]:
        markets = data.get("attachments", {}).get("markets", {})
        return [m for m in markets.values() if m.get("marketName") == market_name]

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> List[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        game_events = self._parse_game_events(data)
        ml_markets = self._get_markets(data, "Moneyline")
        now = datetime.now(timezone.utc).isoformat()

        games: List[Game] = []
        for mkt in ml_markets:
            eid = str(mkt.get("eventId", ""))
            ev = game_events.get(eid)
            if not ev:
                continue
            teams = self._parse_event_teams(ev)
            if not teams:
                continue
            away_clean, home_clean = teams

            home_odds = away_odds = None
            for runner in mkt.get("runners", []):
                name = runner.get("runnerName", "")
                val = _parse_american(
                    runner.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds")
                )
                if val is None:
                    continue
                if name in home_clean or home_clean in name:
                    home_odds = val
                elif name in away_clean or away_clean in name:
                    away_odds = val

            if home_odds is None and away_odds is None:
                continue

            games.append(Game(
                sport=sport.value, home_team=home_clean, away_team=away_clean,
                start_time=ev.get("openDate"), game_id=str(eid),
                lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
            ))

        logger.info("FanDuel %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> List[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        game_events = self._parse_game_events(data)
        market_name = "Run Line" if sport == Sport.MLB else "Spread"
        spread_markets = self._get_markets(data, market_name)
        now = datetime.now(timezone.utc).isoformat()

        games: List[Game] = []
        for mkt in spread_markets:
            eid = str(mkt.get("eventId", ""))
            ev = game_events.get(eid)
            if not ev:
                continue
            teams = self._parse_event_teams(ev)
            if not teams:
                continue
            away_clean, home_clean = teams

            home_spread = away_spread = None
            home_spread_odds = away_spread_odds = None
            for runner in mkt.get("runners", []):
                name = runner.get("runnerName", "")
                val = _parse_american(
                    runner.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds")
                )
                handicap = runner.get("handicap")
                if val is None:
                    continue
                if name in home_clean or home_clean in name:
                    home_spread = handicap
                    home_spread_odds = val
                elif name in away_clean or away_clean in name:
                    away_spread = handicap
                    away_spread_odds = val

            if home_spread_odds is None and away_spread_odds is None:
                continue

            games.append(Game(
                sport=sport.value, home_team=home_clean, away_team=away_clean,
                start_time=ev.get("openDate"), game_id=str(eid),
                lines=[Line(
                    book=self.name,
                    home_spread=home_spread, away_spread=away_spread,
                    home_spread_odds=home_spread_odds, away_spread_odds=away_spread_odds,
                    fetched_at=now,
                )],
            ))

        logger.info("FanDuel %s spreads: %d games", sport.value, len(games))
        return games

    # -- Totals --

    def fetch_totals(self, sport: Sport) -> List[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        game_events = self._parse_game_events(data)
        total_markets = self._get_markets(data, "Total Runs" if sport == Sport.MLB else "Total Points")
        now = datetime.now(timezone.utc).isoformat()

        games: List[Game] = []
        for mkt in total_markets:
            eid = str(mkt.get("eventId", ""))
            ev = game_events.get(eid)
            if not ev:
                continue
            teams = self._parse_event_teams(ev)
            if not teams:
                continue
            away_clean, home_clean = teams

            total = None
            over_odds = under_odds = None
            for runner in mkt.get("runners", []):
                name = runner.get("runnerName", "").lower()
                val = _parse_american(
                    runner.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds")
                )
                handicap = runner.get("handicap")
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

            games.append(Game(
                sport=sport.value, home_team=home_clean, away_team=away_clean,
                start_time=ev.get("openDate"), game_id=str(eid),
                lines=[Line(book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now)],
            ))

        logger.info("FanDuel %s totals: %d games", sport.value, len(games))
        return games
