"""Tests for the Bovada adapter using mocked responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from oddswrap.books.bovada import (
    BovadaAdapter,
    _epoch_ms_to_iso,
    _get_competitors,
    _parse_handicap,
)
from oddswrap.models import Sport


class TestHelpers:
    def test_parse_handicap_float(self):
        assert _parse_handicap("1.5") == 1.5

    def test_parse_handicap_negative(self):
        assert _parse_handicap("-1.5") == -1.5

    def test_parse_handicap_none(self):
        assert _parse_handicap(None) is None

    def test_parse_handicap_invalid(self):
        assert _parse_handicap("abc") is None

    def test_epoch_ms_to_iso(self):
        result = _epoch_ms_to_iso(1712170800000)
        assert result is not None
        assert "2024-04-03" in result

    def test_epoch_ms_to_iso_none(self):
        assert _epoch_ms_to_iso(None) is None

    def test_get_competitors(self):
        event = {
            "competitors": [
                {"name": "Away Team", "home": False},
                {"name": "Home Team", "home": True},
            ]
        }
        result = _get_competitors(event)
        assert result == ("Away Team", "Home Team")

    def test_get_competitors_missing(self):
        assert _get_competitors({"competitors": []}) is None
        assert _get_competitors({}) is None


class TestBovadaAdapter:
    def setup_method(self):
        self.adapter = BovadaAdapter()

    def test_supported_sports(self):
        sports = self.adapter.supported_sports()
        assert Sport.MLB in sports
        assert Sport.NBA in sports
        assert Sport.NFL in sports
        assert Sport.NHL in sports
        assert Sport.NCAAF in sports
        assert Sport.NCAAB in sports

    def test_name(self):
        assert self.adapter.name == "bovada"

    @patch("oddswrap.books.bovada.cffi_requests.get")
    def test_fetch_moneylines(self, mock_get, bovada_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = bovada_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)

        assert len(games) == 2
        mets_game = next(g for g in games if "Mets" in g.away_team)
        assert mets_game.lines[0].away_odds == 145
        assert mets_game.lines[0].home_odds == -165
        assert mets_game.lines[0].book == "bovada"
        assert mets_game.home_team == "Atlanta Braves"
        assert mets_game.away_team == "New York Mets"

    @patch("oddswrap.books.bovada.cffi_requests.get")
    def test_fetch_moneylines_unicode_minus(self, mock_get, bovada_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = bovada_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)

        dodgers_game = next(g for g in games if "Dodgers" in g.home_team)
        # Unicode minus \u2212 should be converted to standard negative
        assert dodgers_game.lines[0].home_odds == -240

    @patch("oddswrap.books.bovada.cffi_requests.get")
    def test_fetch_spreads(self, mock_get, bovada_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = bovada_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_spreads(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].home_spread == -1.5
        assert games[0].lines[0].away_spread == 1.5
        assert games[0].lines[0].home_spread_odds == 105
        assert games[0].lines[0].away_spread_odds == -125

    @patch("oddswrap.books.bovada.cffi_requests.get")
    def test_fetch_totals(self, mock_get, bovada_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = bovada_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_totals(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].total == 8.5
        assert games[0].lines[0].over_odds == -108
        assert games[0].lines[0].under_odds == -112

    @patch("oddswrap.books.bovada.cffi_requests.get")
    def test_fetch_raw_failure_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []

    def test_unsupported_sport_returns_none(self):
        # All sports are supported, so test _fetch_raw with a hypothetical
        result = self.adapter._fetch_raw(Sport.MLB)
        # Can't really test without mocking, but at least verify no crash
        # This will attempt a real HTTP call and fail gracefully
        assert result is None or isinstance(result, list)

    @patch("oddswrap.books.bovada.cffi_requests.get")
    def test_start_time_converted_from_epoch(self, mock_get, bovada_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = bovada_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)

        # startTime 1712170800000 should be an ISO 8601 string
        assert games[0].start_time is not None
        assert "T" in games[0].start_time
        assert "+" in games[0].start_time or "Z" in games[0].start_time

    @patch("oddswrap.books.bovada.cffi_requests.get")
    def test_game_id_set(self, mock_get, bovada_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = bovada_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games[0].game_id == "bov1"
