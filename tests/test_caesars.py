"""Tests for the Caesars adapter using mocked responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from oddswrap.books.caesars import CaesarsAdapter, _decimal_to_american, _parse_american
from oddswrap.models import Sport


@pytest.fixture()
def czr_raw_response():
    """Minimal Caesars API response."""
    return {
        "competitions": [
            {
                "events": [
                    {
                        "id": "evt-001",
                        "name": "San Diego Padres @ Boston Red Sox",
                        "startTime": "2026-04-03T18:10:00Z",
                        "competitors": [
                            {"name": "San Diego Padres", "type": "away"},
                            {"name": "Boston Red Sox", "type": "home"},
                        ],
                        "markets": [
                            {
                                "name": "Moneyline",
                                "active": True,
                                "display": True,
                                "selections": [
                                    {"name": "San Diego Padres", "price": {"a": "+102", "d": 2.02}},
                                    {"name": "Boston Red Sox", "price": {"a": "-120", "d": 1.83}},
                                ],
                            },
                            {
                                "name": "Run Line",
                                "active": True,
                                "display": True,
                                "line": 1.5,
                                "selections": [
                                    {"name": "San Diego Padres", "price": {"a": "+145", "d": 2.45}, "handicap": -1.5},
                                    {"name": "Boston Red Sox", "price": {"a": "-170", "d": 1.59}, "handicap": 1.5},
                                ],
                            },
                            {
                                "name": "Total Runs",
                                "active": True,
                                "display": True,
                                "line": 8.5,
                                "selections": [
                                    {"name": "Over 8.5", "price": {"a": "-110", "d": 1.91}, "handicap": 8.5},
                                    {"name": "Under 8.5", "price": {"a": "-110", "d": 1.91}, "handicap": 8.5},
                                ],
                            },
                        ],
                    },
                    {
                        "id": "evt-002",
                        "name": "New York Mets @ Atlanta Braves",
                        "startTime": "2026-04-03T20:00:00Z",
                        "competitors": [
                            {"name": "New York Mets", "type": "away"},
                            {"name": "Atlanta Braves", "type": "home"},
                        ],
                        "markets": [
                            {
                                "name": "Moneyline",
                                "active": True,
                                "display": True,
                                "selections": [
                                    {"name": "New York Mets", "price": {"a": "+150", "d": 2.50}},
                                    {"name": "Atlanta Braves", "price": {"a": "-170", "d": 1.59}},
                                ],
                            },
                        ],
                    },
                ],
            }
        ],
    }


class TestParseAmerican:
    def test_positive(self):
        assert _parse_american("+102") == 102

    def test_negative(self):
        assert _parse_american("-120") == -120

    def test_none(self):
        assert _parse_american(None) is None


class TestDecimalToAmerican:
    def test_favorite(self):
        assert _decimal_to_american(1.5) == -200

    def test_underdog(self):
        assert _decimal_to_american(2.5) == 150

    def test_even(self):
        assert _decimal_to_american(2.0) == 100


class TestCaesarsAdapter:
    def setup_method(self):
        self.adapter = CaesarsAdapter()

    def test_supported_sports(self):
        sports = self.adapter.supported_sports()
        assert Sport.MLB in sports
        assert Sport.NBA in sports
        assert Sport.NFL in sports
        assert Sport.NHL in sports

    def test_name(self):
        assert self.adapter.name == "caesars"

    @patch("oddswrap.books.caesars.cffi_requests.get")
    def test_fetch_moneylines(self, mock_get, czr_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = czr_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)

        assert len(games) == 2
        padres_game = next(g for g in games if "Padres" in g.away_team)
        assert padres_game.lines[0].away_odds == 102
        assert padres_game.lines[0].home_odds == -120
        assert padres_game.lines[0].book == "caesars"

    @patch("oddswrap.books.caesars.cffi_requests.get")
    def test_fetch_spreads(self, mock_get, czr_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = czr_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_spreads(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].home_spread == 1.5
        assert games[0].lines[0].away_spread == -1.5
        assert games[0].lines[0].home_spread_odds == -170
        assert games[0].lines[0].away_spread_odds == 145

    @patch("oddswrap.books.caesars.cffi_requests.get")
    def test_fetch_totals(self, mock_get, czr_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = czr_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_totals(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].total == 8.5
        assert games[0].lines[0].over_odds == -110
        assert games[0].lines[0].under_odds == -110

    @patch("oddswrap.books.caesars.cffi_requests.get")
    def test_fetch_raw_failure_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []

    def test_unsupported_sport_returns_none(self):
        result = self.adapter._fetch_raw(Sport.NCAAF)
        assert result is None
