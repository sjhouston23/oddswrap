"""Tests for the BetMGM adapter using mocked responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from oddswrap.books.betmgm import BetMGMAdapter, _parse_handicap, _parse_option_odds
from oddswrap.models import Sport


class TestHelpers:
    def test_parse_option_odds_american(self):
        option = {"price": {"americanOdds": 150, "odds": 2.50}}
        val = _parse_option_odds(option)
        assert val == 150

    def test_parse_option_odds_negative(self):
        option = {"price": {"americanOdds": -161, "odds": 1.62}}
        val = _parse_option_odds(option)
        assert val == -161

    def test_parse_option_odds_none(self):
        assert _parse_option_odds({"price": {}}) is None
        assert _parse_option_odds({}) is None

    def test_parse_handicap_positive(self):
        assert _parse_handicap("+1.5") == 1.5

    def test_parse_handicap_negative(self):
        assert _parse_handicap("-1.5") == -1.5

    def test_parse_handicap_none(self):
        assert _parse_handicap(None) is None


class TestBetMGMAdapter:
    def setup_method(self):
        self.adapter = BetMGMAdapter()
        # Pre-set access ID and grid groups to skip discovery calls in tests
        self.adapter._access_id = "test-access-id"
        self.adapter._grid_groups = {23: {"money line": "ml-id"}}

    def test_supported_sports(self):
        sports = self.adapter.supported_sports()
        assert Sport.MLB in sports
        assert Sport.NBA in sports
        assert Sport.NFL in sports
        assert Sport.NHL in sports

    def test_name(self):
        assert self.adapter.name == "betmgm"

    @patch("oddswrap.books.betmgm.cffi_requests.get")
    def test_fetch_moneylines(self, mock_get, betmgm_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = betmgm_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)

        assert len(games) == 2
        mets_game = next(g for g in games if "Mets" in g.away_team)
        assert mets_game.lines[0].book == "betmgm"
        assert mets_game.lines[0].away_odds is not None
        assert mets_game.lines[0].home_odds is not None
        assert mets_game.home_team == "Atlanta Braves"
        assert mets_game.away_team == "New York Mets"

    @patch("oddswrap.books.betmgm.cffi_requests.get")
    def test_fetch_spreads(self, mock_get, betmgm_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = betmgm_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_spreads(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].home_spread == -1.5
        assert games[0].lines[0].away_spread == 1.5
        assert games[0].lines[0].home_spread_odds is not None
        assert games[0].lines[0].away_spread_odds is not None

    @patch("oddswrap.books.betmgm.cffi_requests.get")
    def test_fetch_totals(self, mock_get, betmgm_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = betmgm_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_totals(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].total == 8.5
        assert games[0].lines[0].over_odds is not None
        assert games[0].lines[0].under_odds is not None

    @patch("oddswrap.books.betmgm.cffi_requests.get")
    def test_fetch_raw_failure_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []

    def test_unsupported_sport_returns_none(self):
        result = self.adapter._fetch_raw(Sport.NCAAF)
        assert result is None

    @patch("oddswrap.books.betmgm.cffi_requests.get")
    def test_start_time(self, mock_get, betmgm_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = betmgm_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games[0].start_time == "2026-04-03T18:00:00Z"

    @patch("oddswrap.books.betmgm.cffi_requests.get")
    def test_game_id(self, mock_get, betmgm_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = betmgm_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games[0].game_id == "mgm1"

    @patch("oddswrap.books.betmgm.cffi_requests.get")
    def test_suspended_markets_skipped(self, mock_get):
        """Markets with status != Visible should be skipped."""
        data = {
            "fixtures": [
                {
                    "id": "fix1",
                    "name": {"value": "Team A at Team B"},
                    "startDate": "2026-04-03T18:00:00Z",
                    "participants": [
                        {"name": {"value": "Team A"}, "properties": {"type": "AwayTeam"}},
                        {"name": {"value": "Team B"}, "properties": {"type": "HomeTeam"}},
                    ],
                    "optionMarkets": [
                        {
                            "id": 1,
                            "name": {"value": "Moneyline"},
                            "status": "Suspended",
                            "options": [
                                {"name": {"value": "Team A"}, "status": "Visible", "price": {"americanOdds": 100}},
                                {"name": {"value": "Team B"}, "status": "Visible", "price": {"americanOdds": -120}},
                            ],
                        }
                    ],
                    "games": [],
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = data
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []
