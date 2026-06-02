"""FanDuel Sportsbook adapter."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, PlayerProp, PropCategory, Sport, normalize_start_time, parse_american

logger = logging.getLogger("oddswrap.fanduel")

# FanDuel sbapi — customPageId per sport
_PAGE_IDS: dict[Sport, str] = {
    Sport.MLB: "mlb",
    Sport.NBA: "nba",
    Sport.NFL: "nfl",
    Sport.NHL: "nhl",
}

_BASE_URL = "https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"
_EVENT_URL = "https://sbapi.nj.sportsbook.fanduel.com/api/event-page"
_API_KEY = "FhMFpcPWXMeyZxOx"

# Tab on the event page where player props live
_PROPS_TAB = "popular"

# Matches "N+" inside a market name like "To Record 2+ Hits" / "To Hit 2+ Home Runs"
_THRESHOLD_RE = re.compile(r"(\d+)\+")


def _line_from_market_name(name: str) -> float | None:
    """Derive an O/U-equivalent line from a FanDuel threshold market name.

    "To Record 2+ Hits" -> 1.5, "To Hit A Home Run" -> 0.5 (1+), else None.
    """
    match = _THRESHOLD_RE.search(name)
    if match:
        return int(match.group(1)) - 0.5
    # Singular phrasing ("A"/"An") means 1+ → line 0.5
    if re.search(r"\b(a|an)\b", name, re.IGNORECASE):
        return 0.5
    return None


class FanDuelAdapter(BookAdapter):
    name = "fanduel"

    def supported_sports(self) -> list[Sport]:
        return list(_PAGE_IDS.keys())

    def _fetch_raw(self, sport: Sport) -> dict | None:
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

    def _parse_game_events(self, data: dict) -> dict[str, dict]:
        events = data.get("attachments", {}).get("events", {})
        return {str(eid): ev for eid, ev in events.items() if " @ " in ev.get("name", "")}

    def _parse_event_teams(self, ev: dict) -> tuple[str, str] | None:
        name = ev.get("name", "")
        parts = name.split(" @ ", 1)
        if len(parts) != 2:
            return None
        away = parts[0].strip().split(" (")[0].strip()
        home = parts[1].strip().split(" (")[0].strip()
        return away, home

    def _get_markets(self, data: dict, market_name: str) -> list[dict]:
        markets = data.get("attachments", {}).get("markets", {})
        return [m for m in markets.values() if m.get("marketName") == market_name]

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        game_events = self._parse_game_events(data)
        ml_markets = self._get_markets(data, "Moneyline")
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
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
                val = parse_american(runner.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds"))
                if val is None:
                    continue
                if name in home_clean or home_clean in name:
                    home_odds = val
                elif name in away_clean or away_clean in name:
                    away_odds = val

            if home_odds is None and away_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_clean,
                    away_team=away_clean,
                    start_time=normalize_start_time(ev.get("openDate")),
                    game_id=str(eid),
                    lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
                )
            )

        logger.info("FanDuel %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        game_events = self._parse_game_events(data)
        market_name = "Run Line" if sport == Sport.MLB else "Spread"
        spread_markets = self._get_markets(data, market_name)
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
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
                val = parse_american(runner.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds"))
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

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_clean,
                    away_team=away_clean,
                    start_time=normalize_start_time(ev.get("openDate")),
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

        logger.info("FanDuel %s spreads: %d games", sport.value, len(games))
        return games

    # -- Totals --

    def fetch_totals(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        game_events = self._parse_game_events(data)
        total_markets = self._get_markets(data, "Total Runs" if sport == Sport.MLB else "Total Points")
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
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
                val = parse_american(runner.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds"))
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

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_clean,
                    away_team=away_clean,
                    start_time=normalize_start_time(ev.get("openDate")),
                    game_id=str(eid),
                    lines=[
                        Line(book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now)
                    ],
                )
            )

        logger.info("FanDuel %s totals: %d games", sport.value, len(games))
        return games

    # -- Player Props --

    def _fetch_event_page(self, event_id: str, tab: str) -> dict | None:
        try:
            resp = cffi_requests.get(
                _EVENT_URL,
                params={"eventId": event_id, "tab": tab, "_ak": _API_KEY},
                impersonate="chrome120",
                headers={"Accept": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("FanDuel event-page fetch failed for %s: %s", event_id, exc)
            return None

    @staticmethod
    def _is_player_prop_market(mkt: dict) -> bool:
        """A player-prop market has runners flagged as player selections."""
        runners = mkt.get("runners", [])
        return bool(runners) and any(r.get("isPlayerSelection") for r in runners)

    def fetch_prop_categories(self, sport: Sport) -> list[PropCategory]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        game_events = self._parse_game_events(data)
        if not game_events:
            return []

        # Inspect one event's props tab to enumerate player-prop market names
        sample_eid = next(iter(game_events))
        page = self._fetch_event_page(sample_eid, _PROPS_TAB)
        if not page:
            return []

        markets = page.get("attachments", {}).get("markets", {})
        seen: set[str] = set()
        results: list[PropCategory] = []
        for m in markets.values():
            if not self._is_player_prop_market(m):
                continue
            mname = m.get("marketName", "")
            if not mname or mname in seen:
                continue
            seen.add(mname)
            results.append(
                PropCategory(
                    book=self.name,
                    category_id=_PROPS_TAB,
                    category_name="Player Props",
                    subcategory_id=mname,
                    subcategory_name=mname,
                )
            )
        return results

    def fetch_props(self, sport: Sport, category_id: str, subcategory_id: str | None = None) -> list[PlayerProp]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        game_events = self._parse_game_events(data)
        if not game_events:
            return []

        tab = category_id or _PROPS_TAB
        now = datetime.now(timezone.utc).isoformat()

        def _fetch(eid: str) -> list[PlayerProp]:
            page = self._fetch_event_page(eid, tab)
            if not page:
                return []
            ev = game_events.get(eid, {})
            game_name = None
            teams = self._parse_event_teams(ev)
            if teams:
                game_name = f"{teams[0]} @ {teams[1]}"

            out: list[PlayerProp] = []
            markets = page.get("attachments", {}).get("markets", {})
            for m in markets.values():
                if not self._is_player_prop_market(m):
                    continue
                mname = m.get("marketName", "")
                if subcategory_id and mname != subcategory_id:
                    continue
                line = _line_from_market_name(mname)
                for runner in m.get("runners", []):
                    if not runner.get("isPlayerSelection"):
                        continue
                    val = parse_american(
                        runner.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds")
                    )
                    if val is None:
                        continue
                    out.append(
                        PlayerProp(
                            book=self.name,
                            player=runner.get("runnerName", ""),
                            market=mname,
                            line=line,
                            over_odds=val,
                            under_odds=None,
                            game=game_name,
                            event_id=eid,
                            fetched_at=now,
                        )
                    )
            return out

        props: list[PlayerProp] = []
        event_ids = list(game_events.keys())
        with ThreadPoolExecutor(max_workers=min(len(event_ids), 8)) as pool:
            for result in pool.map(_fetch, event_ids):
                props.extend(result)

        logger.info("FanDuel %s props: %d", sport.value, len(props))
        return props
