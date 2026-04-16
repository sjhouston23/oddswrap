"""DraftKings Sportsbook adapter."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, PlayerProp, PropCategory, Sport, normalize_start_time, parse_american

logger = logging.getLogger("oddswrap.draftkings")

# sportscontent API — league IDs per sport
_LEAGUE_IDS: dict[Sport, int] = {
    Sport.MLB: 84240,
    Sport.NBA: 42648,
    Sport.NFL: 88808,
    Sport.NHL: 42133,
}

_CATEGORY_ID = 493  # Full Game lines

_BASE_URL = (
    "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1/leagues/{league_id}/categories/{category_id}"
)

_SUBCAT_URL = (
    "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1"
    "/leagues/{league_id}/categories/{category_id}/subcategories/{subcategory_id}"
)

_LEAGUE_URL = "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1/leagues/{league_id}"


class DraftKingsAdapter(BookAdapter):
    name = "draftkings"

    def supported_sports(self) -> list[Sport]:
        return list(_LEAGUE_IDS.keys())

    def _fetch_raw(self, sport: Sport) -> dict | None:
        league_id = _LEAGUE_IDS.get(sport)
        if league_id is None:
            return None
        url = _BASE_URL.format(league_id=league_id, category_id=_CATEGORY_ID)
        try:
            resp = cffi_requests.get(url, impersonate="chrome120", timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("DraftKings fetch failed for %s: %s", sport, exc)
            return None

    def _parse_events(self, data: dict) -> dict[str, dict]:
        return {ev["id"]: ev for ev in data.get("events", [])}

    def _parse_event_teams(self, ev: dict) -> tuple[str, str] | None:
        name = ev.get("name", "")
        if " @ " not in name:
            return None
        parts = name.split(" @ ", 1)
        return parts[0].strip(), parts[1].strip()

    def _group_selections_by_market(self, data: dict, market_name: str) -> dict[str, tuple[str, list]]:
        """Returns {market_id: (event_id, [selections])} for markets matching name."""
        markets = data.get("markets", [])
        selections = data.get("selections", [])

        target_markets: dict[str, str] = {}
        for mkt in markets:
            if mkt.get("name") == market_name:
                target_markets[mkt["id"]] = mkt["eventId"]

        grouped: dict[str, tuple[str, list]] = {mid: (eid, []) for mid, eid in target_markets.items()}
        for sel in selections:
            mid = sel.get("marketId")
            if mid in grouped:
                grouped[mid][1].append(sel)

        return grouped

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        events = self._parse_events(data)
        grouped = self._group_selections_by_market(data, "Moneyline")
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for _mid, (eid, sels) in grouped.items():
            ev = events.get(eid)
            if not ev:
                continue
            teams = self._parse_event_teams(ev)
            if not teams:
                continue
            away_raw, home_raw = teams

            home_odds = away_odds = None
            for sel in sels:
                label = sel.get("label", "")
                val = parse_american(sel.get("displayOdds", {}).get("american", ""))
                if val is None:
                    continue
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
                    start_time=normalize_start_time(ev.get("startEventDate")),
                    game_id=str(eid),
                    lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
                )
            )

        logger.info("DraftKings %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        events = self._parse_events(data)
        market_name = "Run Line" if sport == Sport.MLB else "Spread"
        grouped = self._group_selections_by_market(data, market_name)
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for _mid, (eid, sels) in grouped.items():
            ev = events.get(eid)
            if not ev:
                continue
            teams = self._parse_event_teams(ev)
            if not teams:
                continue
            away_raw, home_raw = teams

            home_spread = away_spread = None
            home_spread_odds = away_spread_odds = None
            for sel in sels:
                label = sel.get("label", "")
                val = parse_american(sel.get("displayOdds", {}).get("american", ""))
                # Extract spread value from label, e.g. "NYY Yankees -1.5"
                points = sel.get("points")
                if val is None:
                    continue
                if label in home_raw or home_raw in label or (home_raw.split()[-1] in label):
                    home_spread = points
                    home_spread_odds = val
                elif label in away_raw or away_raw in label or (away_raw.split()[-1] in label):
                    away_spread = points
                    away_spread_odds = val

            if home_spread_odds is None and away_spread_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_raw,
                    away_team=away_raw,
                    start_time=normalize_start_time(ev.get("startEventDate")),
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

        logger.info("DraftKings %s spreads: %d games", sport.value, len(games))
        return games

    # -- Totals --

    def fetch_totals(self, sport: Sport) -> list[Game]:
        data = self._fetch_raw(sport)
        if not data:
            return []
        events = self._parse_events(data)
        grouped = self._group_selections_by_market(data, "Total")
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for _mid, (eid, sels) in grouped.items():
            ev = events.get(eid)
            if not ev:
                continue
            teams = self._parse_event_teams(ev)
            if not teams:
                continue
            away_raw, home_raw = teams

            total = None
            over_odds = under_odds = None
            for sel in sels:
                label = sel.get("label", "").lower()
                val = parse_american(sel.get("displayOdds", {}).get("american", ""))
                points = sel.get("points")
                if val is None:
                    continue
                if "over" in label:
                    over_odds = val
                    total = points
                elif "under" in label:
                    under_odds = val
                    if total is None:
                        total = points

            if over_odds is None and under_odds is None:
                continue

            games.append(
                Game(
                    sport=sport.value,
                    home_team=home_raw,
                    away_team=away_raw,
                    start_time=normalize_start_time(ev.get("startEventDate")),
                    game_id=str(eid),
                    lines=[
                        Line(book=self.name, total=total, over_odds=over_odds, under_odds=under_odds, fetched_at=now)
                    ],
                )
            )

        logger.info("DraftKings %s totals: %d games", sport.value, len(games))
        return games

    # -- Player Props --

    def fetch_prop_categories(self, sport: Sport) -> list[PropCategory]:
        league_id = _LEAGUE_IDS.get(sport)
        if league_id is None:
            return []
        url = _LEAGUE_URL.format(league_id=league_id)
        try:
            resp = cffi_requests.get(url, impersonate="chrome120", timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("DraftKings prop categories failed for %s: %s", sport, exc)
            return []

        categories = data.get("categories", [])
        subcategories = data.get("subcategories", [])

        # Build subcategory lookup by categoryId
        subcat_by_cat: dict[int, list[dict]] = {}
        for sc in subcategories:
            cid = sc.get("categoryId")
            if cid:
                subcat_by_cat.setdefault(cid, []).append(sc)

        results: list[PropCategory] = []
        for cat in categories:
            cid = cat.get("id")
            cname = cat.get("name", "")
            # Skip game-level categories (already covered by get_moneylines etc.)
            if cid == _CATEGORY_ID:
                continue
            subs = subcat_by_cat.get(cid, [])
            if subs:
                for sc in subs:
                    results.append(
                        PropCategory(
                            book=self.name,
                            category_id=str(cid),
                            category_name=cname,
                            subcategory_id=str(sc["id"]),
                            subcategory_name=sc.get("name", ""),
                        )
                    )
            else:
                results.append(
                    PropCategory(book=self.name, category_id=str(cid), category_name=cname)
                )

        return results

    def fetch_props(self, sport: Sport, category_id: str, subcategory_id: str | None = None) -> list[PlayerProp]:
        league_id = _LEAGUE_IDS.get(sport)
        if league_id is None:
            return []

        if subcategory_id:
            url = _SUBCAT_URL.format(
                league_id=league_id, category_id=category_id, subcategory_id=subcategory_id
            )
        else:
            url = _BASE_URL.format(league_id=league_id, category_id=category_id)

        try:
            resp = cffi_requests.get(url, impersonate="chrome120", timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("DraftKings props fetch failed: %s", exc)
            return []

        events = {ev["id"]: ev for ev in data.get("events", [])}
        markets = data.get("markets", [])
        selections = data.get("selections", [])
        now = datetime.now(timezone.utc).isoformat()

        # Group selections by market
        mkt_sels: dict[str, list[dict]] = {}
        for sel in selections:
            mkt_sels.setdefault(sel.get("marketId"), []).append(sel)

        props: list[PlayerProp] = []
        for mkt in markets:
            mid = mkt["id"]
            eid = mkt.get("eventId")
            ev = events.get(eid, {})
            game_name = ev.get("name")
            mkt_name = mkt.get("name", "")

            sels = mkt_sels.get(mid, [])
            over_odds = under_odds = None
            line = None
            player = mkt_name

            for sel in sels:
                label = sel.get("label", "")
                odds_str = sel.get("displayOdds", {}).get("american", "")
                val = parse_american(odds_str)
                points = sel.get("points")

                if "Over" in label:
                    over_odds = val
                    line = points
                elif "Under" in label:
                    under_odds = val
                    if line is None:
                        line = points

            if over_odds is None and under_odds is None:
                continue

            props.append(
                PlayerProp(
                    book=self.name,
                    player=player,
                    market=mkt_name,
                    line=line,
                    over_odds=over_odds,
                    under_odds=under_odds,
                    game=game_name,
                    event_id=str(eid) if eid else None,
                    fetched_at=now,
                )
            )

        logger.info("DraftKings %s props: %d", sport.value, len(props))
        return props
