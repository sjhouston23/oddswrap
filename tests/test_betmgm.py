"""Tests for the BetMGM adapter using mocked responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from oddswrap.books.betmgm import BetMGMAdapter, _parse_handicap, _parse_result_odds
from oddswrap.models import Sport


class TestHelpers:
    def test_parse_result_odds_decimal(self):
        # 2.40 decimal → +140
        result = {"odds": 2.40}
        val = _parse_result_odds(result)
        assert val == 140

    def test_parse_result_odds_american_preferred(self):
        # americanOdds takes precedence over decimal
        result = {"americanOdds": "+150", "odds": 2.50}
        val = _parse_result_odds(result)
        assert val == 150

    def test_parse_result_odds_negative(self):
        result = {"odds": 1.62}
        val = _parse_result_odds(result)
        assert val is not None
        assert val < 0

    def test_parse_result_odds_none(self):
        assert _parse_result_odds({}) is None

    def test_parse_handicap_positive(self):
        assert _parse_handicap("1.5") == 1.5

    def test_parse_handicap_negative(self):
        assert _parse_handicap("-1.5") == -1.5

    def test_parse_handicap_none(self):
        assert _parse_handicap(None) is None


class TestBetMGMAdapter:
    def setup_method(self):
        self.adapter = BetMGMAdapter()

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
    def test_hidden_markets_skipped(self, mock_get):
        """Markets with visibility != Visible should be skipped."""
        data = {
            "fixtures": [
                {
                    "id": "fix1",
                    "participants": [
                        {"name": {"value": "Team A"}, "properties": {"type": "AWAY"}},
                        {"name": {"value": "Team B"}, "properties": {"type": "HOME"}},
                    ],
                    "games": [
                        {
                            "name": {"value": "Moneyline"},
                            "visibility": "Hidden",
                            "results": [
                                {"name": {"value": "Team A"}, "odds": 2.00, "visibility": "Visible"},
                                {"name": {"value": "Team B"}, "odds": 1.80, "visibility": "Visible"},
                            ],
                        }
                    ],
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = data
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []
