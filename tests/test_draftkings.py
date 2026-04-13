"""Tests for the DraftKings adapter using mocked responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from oddswrap.books.draftkings import DraftKingsAdapter
from oddswrap.models import Sport, parse_american


class TestParseAmerican:
    def test_positive(self):
        assert parse_american("+150") == 150

    def test_negative(self):
        assert parse_american("-170") == -170

    def test_unicode_minus(self):
        assert parse_american("\u2212250") == -250

    def test_invalid(self):
        assert parse_american("EVEN") is None

    def test_none(self):
        assert parse_american(None) is None


class TestDraftKingsAdapter:
    def setup_method(self):
        self.adapter = DraftKingsAdapter()

    def test_supported_sports(self):
        sports = self.adapter.supported_sports()
        assert Sport.MLB in sports
        assert Sport.NBA in sports
        assert Sport.NFL in sports
        assert Sport.NHL in sports
        assert Sport.NCAAF not in sports

    def test_name(self):
        assert self.adapter.name == "draftkings"

    @patch("oddswrap.books.draftkings.cffi_requests.get")
    def test_fetch_moneylines(self, mock_get, dk_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = dk_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)

        assert len(games) == 2
        mets_game = next(g for g in games if "Mets" in g.away_team)
        assert mets_game.lines[0].away_odds == 150
        assert mets_game.lines[0].home_odds == -170
        assert mets_game.lines[0].book == "draftkings"

    @patch("oddswrap.books.draftkings.cffi_requests.get")
    def test_fetch_spreads(self, mock_get, dk_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = dk_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_spreads(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].home_spread == -1.5
        assert games[0].lines[0].away_spread == 1.5

    @patch("oddswrap.books.draftkings.cffi_requests.get")
    def test_fetch_totals(self, mock_get, dk_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = dk_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_totals(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].total == 8.5
        assert games[0].lines[0].over_odds == -110
        assert games[0].lines[0].under_odds == -110

    @patch("oddswrap.books.draftkings.cffi_requests.get")
    def test_fetch_raw_failure_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []

    def test_unsupported_sport_returns_none(self):
        result = self.adapter._fetch_raw(Sport.NCAAF)
        assert result is None
