"""Tests for oddswrap.client (OddsClient)."""

from __future__ import annotations

from oddswrap.base import BookAdapter
from oddswrap.client import OddsClient
from oddswrap.models import Game, Line, Sport


class FakeAdapter(BookAdapter):
    name = "fake"

    def supported_sports(self):
        return [Sport.MLB]

    def fetch_moneylines(self, sport):
        return [
            Game(
                sport=sport.value,
                home_team="atlanta braves",
                away_team="new york mets",
                start_time="2026-04-03T18:00:00Z",
                game_id="f1",
                lines=[Line(book=self.name, home_odds=-160, away_odds=140)],
            )
        ]

    def fetch_spreads(self, sport):
        return [
            Game(
                sport=sport.value,
                home_team="atlanta braves",
                away_team="new york mets",
                start_time="2026-04-03T18:00:00Z",
                game_id="f1",
                lines=[
                    Line(book=self.name, home_spread=-1.5, away_spread=1.5, home_spread_odds=-130, away_spread_odds=110)
                ],
            )
        ]

    def fetch_totals(self, sport):
        return [
            Game(
                sport=sport.value,
                home_team="atlanta braves",
                away_team="new york mets",
                start_time="2026-04-03T18:00:00Z",
                game_id="f1",
                lines=[Line(book=self.name, total=8.5, over_odds=-110, under_odds=-110)],
            )
        ]


class TestOddsClient:
    def test_get_moneylines(self):
        client = OddsClient(adapters=[FakeAdapter()])
        games = client.get_moneylines("mlb")
        assert len(games) == 1
        assert games[0].lines[0].home_odds == -160

    def test_get_spreads(self):
        client = OddsClient(adapters=[FakeAdapter()])
        games = client.get_spreads(Sport.MLB)
        assert len(games) == 1
        assert games[0].lines[0].home_spread == -1.5

    def test_get_totals(self):
        client = OddsClient(adapters=[FakeAdapter()])
        games = client.get_totals("mlb")
        assert len(games) == 1
        assert games[0].lines[0].total == 8.5

    def test_get_all_merges(self):
        client = OddsClient(adapters=[FakeAdapter()])
        games = client.get_all("mlb")
        # All 3 market types should merge into 1 game with 3 lines
        assert len(games) == 1
        assert len(games[0].lines) == 3

    def test_filter_by_book_name(self):
        client = OddsClient(adapters=[FakeAdapter()], books=["fake"])
        assert client.available_books == ["fake"]

    def test_filter_excludes_unmatched(self):
        client = OddsClient(adapters=[FakeAdapter()], books=["nonexistent"])
        assert client.available_books == []

    def test_available_books(self):
        client = OddsClient(adapters=[FakeAdapter()])
        assert "fake" in client.available_books

    def test_supports(self):
        client = OddsClient(adapters=[FakeAdapter()])
        assert "fake" in client.supports("mlb")
        assert client.supports("nfl") == []

    def test_sport_string_coercion(self):
        client = OddsClient(adapters=[FakeAdapter()])
        # Should accept string and convert to Sport enum
        games = client.get_moneylines("mlb")
        assert len(games) == 1

    def test_merge_across_books(self):
        """Two adapters returning the same game should merge into one Game with 2 lines."""
        fake1 = FakeAdapter()
        fake1.name = "book_a"
        fake2 = FakeAdapter()
        fake2.name = "book_b"
        client = OddsClient(adapters=[fake1, fake2])
        games = client.get_moneylines("mlb")
        assert len(games) == 1
        assert len(games[0].lines) == 2
        books = {line.book for line in games[0].lines}
        assert books == {"book_a", "book_b"}

    def test_series_games_same_utc_date_stay_separate(self):
        """Two games between the same teams on the same UTC date (series games
        played ~21 hours apart) must not be merged together — each book should
        contribute one Line per real game, not two duplicate lines per game.

        Regression test for https://github.com/sjhouston23/oddswrap/issues/6
        """

        class TwoGameAdapter(BookAdapter):
            name = "two_game"

            def supported_sports(self):
                return [Sport.MLB]

            def fetch_moneylines(self, sport):
                return [
                    Game(
                        sport=sport.value,
                        home_team="seattle mariners",
                        away_team="texas rangers",
                        start_time="2026-04-18T01:40:00Z",  # 9:40 PM ET on 4/17
                        game_id="g1",
                        lines=[Line(book=self.name, home_odds=-144, away_odds=122)],
                    ),
                    Game(
                        sport=sport.value,
                        home_team="seattle mariners",
                        away_team="texas rangers",
                        start_time="2026-04-18T23:15:00Z",  # 7:15 PM ET on 4/18
                        game_id="g2",
                        lines=[Line(book=self.name, home_odds=-134, away_odds=114)],
                    ),
                ]

        client = OddsClient(adapters=[TwoGameAdapter()])
        games = client.get_moneylines("mlb")
        assert len(games) == 2, f"expected 2 separate games, got {len(games)}"
        for g in games:
            assert len(g.lines) == 1, f"expected 1 line per game, got {len(g.lines)} in {g.start_time}"

    def test_close_start_times_across_books_still_merge(self):
        """Two adapters reporting the same game with minor time variance (e.g.,
        seconds or a minute apart) should still merge into one Game."""

        class BookA(BookAdapter):
            name = "book_a"

            def supported_sports(self):
                return [Sport.MLB]

            def fetch_moneylines(self, sport):
                return [
                    Game(
                        sport=sport.value,
                        home_team="atlanta braves",
                        away_team="new york mets",
                        start_time="2026-04-03T18:00:46Z",
                        game_id="a",
                        lines=[Line(book=self.name, home_odds=-160, away_odds=140)],
                    )
                ]

        class BookB(BookAdapter):
            name = "book_b"

            def supported_sports(self):
                return [Sport.MLB]

            def fetch_moneylines(self, sport):
                return [
                    Game(
                        sport=sport.value,
                        home_team="atlanta braves",
                        away_team="new york mets",
                        start_time="2026-04-03T18:01:00Z",
                        game_id="b",
                        lines=[Line(book=self.name, home_odds=-155, away_odds=135)],
                    )
                ]

        client = OddsClient(adapters=[BookA(), BookB()])
        games = client.get_moneylines("mlb")
        assert len(games) == 1
        assert len(games[0].lines) == 2
        assert {ln.book for ln in games[0].lines} == {"book_a", "book_b"}
