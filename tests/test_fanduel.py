"""Tests for the FanDuel adapter using mocked responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from oddswrap.books.fanduel import FanDuelAdapter, _parse_american
from oddswrap.models import Sport


class TestParseAmerican:
    def test_positive(self):
        assert _parse_american("+140") == 140

    def test_negative(self):
        assert _parse_american("-165") == -165

    def test_unicode_minus(self):
        assert _parse_american("\u2212230") == -230

    def test_none(self):
        assert _parse_american(None) is None


class TestFanDuelAdapter:
    def setup_method(self):
        self.adapter = FanDuelAdapter()

    def test_supported_sports(self):
        sports = self.adapter.supported_sports()
        assert Sport.MLB in sports
        assert Sport.NBA in sports
        assert Sport.NFL in sports
        assert Sport.NHL in sports

    def test_name(self):
        assert self.adapter.name == "fanduel"

    @patch("oddswrap.books.fanduel.cffi_requests.get")
    def test_fetch_moneylines(self, mock_get, fd_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = fd_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)

        assert len(games) == 2
        mets_game = next(g for g in games if "Mets" in g.away_team)
        assert mets_game.lines[0].away_odds == 140
        assert mets_game.lines[0].home_odds == -165
        assert mets_game.lines[0].book == "fanduel"

    @patch("oddswrap.books.fanduel.cffi_requests.get")
    def test_fetch_spreads(self, mock_get, fd_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = fd_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_spreads(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].home_spread == -1.5
        assert games[0].lines[0].away_spread == 1.5

    @patch("oddswrap.books.fanduel.cffi_requests.get")
    def test_fetch_totals(self, mock_get, fd_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = fd_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_totals(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].total == 8.5
        assert games[0].lines[0].over_odds == -105
        assert games[0].lines[0].under_odds == -115

    @patch("oddswrap.books.fanduel.cffi_requests.get")
    def test_fetch_raw_failure_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []

    @patch("oddswrap.books.fanduel.cffi_requests.get")
    def test_strips_starter_info(self, mock_get, fd_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = fd_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        mets_game = next(g for g in games if "Mets" in g.away_team)
        # Starter info "(S Manaea)" should be stripped
        assert "(" not in mets_game.away_team
        assert "(" not in mets_game.home_team
