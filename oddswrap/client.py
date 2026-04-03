"""Unified odds client — fetches from all registered sportsbooks and merges."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from oddswrap.base import BookAdapter
from oddswrap.books.betmgm import BetMGMAdapter
from oddswrap.books.betrivers import BetRiversAdapter
from oddswrap.books.caesars import CaesarsAdapter
from oddswrap.books.draftkings import DraftKingsAdapter
from oddswrap.books.fanduel import FanDuelAdapter
from oddswrap.books.thescore import TheScoreAdapter
from oddswrap.models import Game, Sport
from oddswrap.normalize import normalize_team

logger = logging.getLogger("oddswrap")

_DEFAULT_ADAPTERS: list[BookAdapter] = [
    DraftKingsAdapter(),
    FanDuelAdapter(),
    BetMGMAdapter(),
    BetRiversAdapter(),
    CaesarsAdapter(),
    TheScoreAdapter(),
]


class OddsClient:
    """Fetch and merge odds from multiple sportsbooks.

    Usage:
        client = OddsClient()
        games = client.get_moneylines("mlb")
        games = client.get_spreads("mlb")
        games = client.get_totals("mlb")
        games = client.get_all("mlb")  # all markets merged

        # Only specific books:
        client = OddsClient(books=["draftkings"])
    """

    def __init__(
        self,
        adapters: list[BookAdapter] | None = None,
        books: list[str] | None = None,
    ):
        all_adapters = adapters or _DEFAULT_ADAPTERS
        if books:
            book_set = set(b.lower() for b in books)
            all_adapters = [a for a in all_adapters if a.name in book_set]
        self.adapters = all_adapters

    def get_moneylines(self, sport: str | Sport) -> list[Game]:
        """Fetch moneyline (h2h) odds from all books."""
        return self._fetch_market(sport, "fetch_moneylines")

    def get_spreads(self, sport: str | Sport) -> list[Game]:
        """Fetch spread / run-line odds from all books."""
        return self._fetch_market(sport, "fetch_spreads")

    def get_totals(self, sport: str | Sport) -> list[Game]:
        """Fetch over/under totals from all books."""
        return self._fetch_market(sport, "fetch_totals")

    def get_all(self, sport: str | Sport) -> list[Game]:
        """Fetch all markets (moneylines + spreads + totals) and merge.

        Each Game may have Lines with different fields populated
        depending on the market type.
        """
        if isinstance(sport, str):
            sport = Sport(sport.lower())

        all_games: list[Game] = []
        for method_name in ("fetch_moneylines", "fetch_spreads", "fetch_totals"):
            all_games.extend(self._fetch_market_raw(sport, method_name))
        return self._merge(all_games)

    def _fetch_market(self, sport: str | Sport, method_name: str) -> list[Game]:
        if isinstance(sport, str):
            sport = Sport(sport.lower())
        raw = self._fetch_market_raw(sport, method_name)
        return self._merge(raw)

    def _fetch_market_raw(self, sport: Sport, method_name: str) -> list[Game]:
        eligible = [a for a in self.adapters if sport in a.supported_sports()]
        if not eligible:
            return []

        all_games: list[Game] = []
        with ThreadPoolExecutor(max_workers=len(eligible)) as pool:

            def _call(adapter: BookAdapter) -> list[Game]:
                fn = getattr(adapter, method_name, None)
                if fn is None:
                    return []
                try:
                    return fn(sport)
                except NotImplementedError:
                    return []

            futures = {pool.submit(_call, a): a for a in eligible}
            for future in as_completed(futures):
                try:
                    all_games.extend(future.result())
                except Exception as exc:
                    logger.warning("Adapter %s failed: %s", futures[future].name, exc)

        return all_games

    def _merge(self, games: list[Game]) -> list[Game]:
        """Merge games from different books by normalized team names."""
        merged: dict[str, Game] = {}

        for game in games:
            norm_away = normalize_team(game.away_team)
            norm_home = normalize_team(game.home_team)
            key = f"{norm_away}@{norm_home}"

            if key not in merged:
                merged[key] = Game(
                    sport=game.sport,
                    home_team=norm_home,
                    away_team=norm_away,
                    start_time=game.start_time,
                    game_id=game.game_id,
                    lines=[],
                )

            if not merged[key].start_time and game.start_time:
                merged[key].start_time = game.start_time

            merged[key].lines.extend(game.lines)

        return list(merged.values())

    @property
    def available_books(self) -> list[str]:
        return [a.name for a in self.adapters]

    def supports(self, sport: str | Sport) -> list[str]:
        if isinstance(sport, str):
            sport = Sport(sport.lower())
        return [a.name for a in self.adapters if sport in a.supported_sports()]
