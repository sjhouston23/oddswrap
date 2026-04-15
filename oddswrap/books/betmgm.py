"""BetMGM Sportsbook adapter (bwin/Entain CDS API).

BetMGM uses the bwin/Entain CDS (Content Delivery Service) API.  Odds are
returned in ``optionMarkets`` within each fixture when the ``gridGroupId``
query parameter is supplied.  The required ``x-bwin-accessid`` is fetched
automatically from BetMGM's client-config endpoint so it stays current when
they rotate the key.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, Sport, normalize_start_time, parse_american

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
_CONFIG_URL = "https://www.{state}.betmgm.com/en/api/clientconfig"
_GRID_URL = "https://sports.{state}.betmgm.com/cds-api/offer-grouping/grid-view/all"

# Fallback access ID — auto-discovery is preferred
_FALLBACK_ACCESS_ID = "ZTllNjllODUtOWQwNS00YmU4LWE4NTEtZGZjOTkzMGM5OWU4"

# Market name mappings (matched against optionMarket.name.value)
_MONEYLINE_NAMES = {"Moneyline", "Money Line"}
_SPREAD_NAMES = {"Run Line Spread", "Run Line", "Point Spread", "Spread", "Puck Line", "Puck Line Spread"}
_TOTAL_NAMES = {"Totals", "Total Runs", "Total Points", "Total Goals", "Total", "Over/Under"}


def _parse_option_odds(option: dict) -> int | None:
    """Extract American odds from an optionMarket option's price."""
    price = option.get("price", {})
    american = price.get("americanOdds")
    if american is not None:
        val = parse_american(str(american))
        if val is not None:
            return val
    return None


def _parse_handicap(val) -> float | None:
    """Parse handicap/attr value."""
    if val is None:
        return None
    try:
        return float(str(val).replace("+", ""))
    except (ValueError, TypeError):
        return None


class BetMGMAdapter(BookAdapter):
    name = "betmgm"

    def __init__(self, state: str = "nj"):
        self._state = state
        self._access_id: str | None = None
        self._grid_groups: dict[int, dict[str, str]] = {}  # {sport_id: {group_name: group_id}}

    def supported_sports(self) -> list[Sport]:
        return list(_COMPETITION_IDS.keys())

    def _get_access_id(self) -> str:
        """Auto-discover the access ID from BetMGM's client config, with fallback."""
        if self._access_id:
            return self._access_id
        try:
            resp = cffi_requests.get(
                _CONFIG_URL.format(state=self._state),
                headers={
                    "x-bwin-browser-url": f"https://www.{self._state}.betmgm.com/en/sports",
                    "X-From-Product": "host-app",
                },
                impersonate="chrome120",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            # Access ID is embedded in msPreloader.groupingUrl as a query param
            grouping_url = data.get("msPreloader", {}).get("groupingUrl", "")
            if "x-bwin-accessid=" in grouping_url:
                self._access_id = grouping_url.split("x-bwin-accessid=")[1].split("&")[0]
                logger.info("BetMGM access ID discovered: %s…", self._access_id[:8])
                return self._access_id
        except Exception as exc:
            logger.warning("BetMGM access ID discovery failed: %s", exc)
        self._access_id = _FALLBACK_ACCESS_ID
        return self._access_id

    def _get_grid_group_id(self, sport: Sport, group_name: str) -> str | None:
        """Get the grid group ID for a given sport and market type."""
        sport_id = int(_SPORT_IDS.get(sport, "0"))
        if sport_id not in self._grid_groups:
            try:
                resp = cffi_requests.get(
                    _GRID_URL.format(state=self._state),
                    params={
                        "x-bwin-accessid": self._get_access_id(),
                        "lang": "en-us",
                        "country": "US",
                        "usercountry": "US",
                    },
                    impersonate="chrome120",
                    timeout=10,
                )
                resp.raise_for_status()
                for item in resp.json():
                    sid = item.get("sportId")
                    groups = {}
                    for g in item.get("groups", []):
                        groups[g["name"].lower()] = g["id"]
                    self._grid_groups[sid] = groups
            except Exception as exc:
                logger.warning("BetMGM grid groups fetch failed: %s", exc)
                return None
        return self._grid_groups.get(sport_id, {}).get(group_name.lower())

    def _fetch_raw(self, sport: Sport, grid_group_id: str | None = None) -> list[dict] | None:
        comp_id = _COMPETITION_IDS.get(sport)
        sport_id = _SPORT_IDS.get(sport)
        if comp_id is None or sport_id is None:
            return None
        url = _BASE_URL.format(state=self._state)
        params = {
            "x-bwin-accessid": self._get_access_id(),
            "lang": "en-us",
            "country": "US",
            "userCountry": "US",
            "offerMapping": "Filtered",
            "sportIds": sport_id,
            "competitionIds": comp_id,
            "fixtureTypes": "Standard",
            "sortBy": "StartDate",
            "offerCategories": "Gridable",
        }
        if grid_group_id:
            params["gridGroupId"] = grid_group_id
        try:
            resp = cffi_requests.get(url, params=params, impersonate="chrome120", timeout=15)
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
            if ptype == "HOMETEAM":
                home = name
            elif ptype == "AWAYTEAM":
                away = name
        if home and away:
            return away, home
        # Fallback: parse "Away at Home" from fixture name
        fname = fixture.get("name", {}).get("value", "")
        if " at " in fname:
            parts = fname.split(" at ", 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
        return None

    def _get_option_markets(self, fixture: dict, market_names: set[str]) -> list[dict]:
        """Filter optionMarkets by name within a fixture."""
        markets = []
        for om in fixture.get("optionMarkets", []):
            if om.get("status") not in ("Visible", "Active"):
                continue
            name = om.get("name", {}).get("value", "")
            if name in market_names:
                markets.append(om)
        return markets

    # -- Moneylines --

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        grid_id = self._get_grid_group_id(sport, "money line")
        fixtures = self._fetch_raw(sport, grid_id)
        if not fixtures:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for fix in fixtures:
            teams = self._get_teams(fix)
            if not teams:
                continue
            away_name, home_name = teams

            for mkt in self._get_option_markets(fix, _MONEYLINE_NAMES):
                home_odds = away_odds = None
                for opt in mkt.get("options", []):
                    if opt.get("status") != "Visible":
                        continue
                    name = opt.get("name", {}).get("value", "")
                    val = _parse_option_odds(opt)
                    if val is None:
                        continue
                    if home_name in name or name in home_name:
                        home_odds = val
                    elif away_name in name or name in away_name:
                        away_odds = val

                if home_odds is None and away_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_name,
                        away_team=away_name,
                        start_time=normalize_start_time(fix.get("startDate")),
                        game_id=str(fix.get("id", "")),
                        lines=[Line(book=self.name, home_odds=home_odds, away_odds=away_odds, fetched_at=now)],
                    )
                )

        logger.info("BetMGM %s moneylines: %d games", sport.value, len(games))
        return games

    # -- Spreads --

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        grid_id = self._get_grid_group_id(sport, "run line spread") or self._get_grid_group_id(sport, "spread")
        fixtures = self._fetch_raw(sport, grid_id)
        if not fixtures:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for fix in fixtures:
            teams = self._get_teams(fix)
            if not teams:
                continue
            away_name, home_name = teams

            for mkt in self._get_option_markets(fix, _SPREAD_NAMES):
                home_spread = away_spread = None
                home_spread_odds = away_spread_odds = None
                for opt in mkt.get("options", []):
                    if opt.get("status") != "Visible":
                        continue
                    name = opt.get("name", {}).get("value", "")
                    val = _parse_option_odds(opt)
                    handicap = _parse_handicap(opt.get("attr"))
                    if val is None:
                        continue
                    if home_name in name or name in home_name:
                        home_spread = handicap
                        home_spread_odds = val
                    elif away_name in name or name in away_name:
                        away_spread = handicap
                        away_spread_odds = val

                if home_spread_odds is None and away_spread_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_name,
                        away_team=away_name,
                        start_time=normalize_start_time(fix.get("startDate")),
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
        grid_id = self._get_grid_group_id(sport, "over/under")
        fixtures = self._fetch_raw(sport, grid_id)
        if not fixtures:
            return []
        now = datetime.now(timezone.utc).isoformat()

        games: list[Game] = []
        for fix in fixtures:
            teams = self._get_teams(fix)
            if not teams:
                continue
            away_name, home_name = teams

            for mkt in self._get_option_markets(fix, _TOTAL_NAMES):
                total = _parse_handicap(mkt.get("attr"))
                over_odds = under_odds = None
                for opt in mkt.get("options", []):
                    if opt.get("status") != "Visible":
                        continue
                    name = opt.get("name", {}).get("value", "").lower()
                    prefix = opt.get("totalsPrefix", "").lower()
                    val = _parse_option_odds(opt)
                    handicap = _parse_handicap(opt.get("attr"))
                    if val is None:
                        continue
                    if "over" in name or prefix == "over":
                        over_odds = val
                        if handicap is not None:
                            total = handicap
                    elif "under" in name or prefix == "under":
                        under_odds = val
                        if total is None and handicap is not None:
                            total = handicap

                if over_odds is None and under_odds is None:
                    continue

                games.append(
                    Game(
                        sport=sport.value,
                        home_team=home_name,
                        away_team=away_name,
                        start_time=normalize_start_time(fix.get("startDate")),
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
