"""Tests for the BetMGM adapter using mocked responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from oddswrap.books.betmgm import BetMGMAdapter, _odds_to_american, _parse_american
from oddswrap.models import Sport


@pytest.fixture()
def mgm_raw_response():
    """Minimal BetMGM CDS API response."""
    return {
        "fixtures": [
            {
                "id": "12345",
                "name": "San Diego Padres at Boston Red Sox",
                "startDate": "2026-04-03T18:10:00Z",
                "participants": [
                    {"name": {"value": "San Diego Padres"}},
                    {"name": {"value": "Boston Red Sox"}},
                ],
                "games": [
                    {
                        "name": {"value": "Moneyline"},
                        "visibility": "Visible",
                        "results": [
                            {"name": {"value": "San Diego Padres"}, "americanOdds": "+102", "odds": 2.02},
                            {"name": {"value": "Boston Red Sox"}, "americanOdds": "-120", "odds": 1.83},
                        ],
                    },
                    {
                        "name": {"value": "Run Line"},
                        "visibility": "Visible",
                        "results": [
                            {
                                "name": {"value": "San Diego Padres"},
                                "americanOdds": "+145",
                                "odds": 2.45,
                                "attr": "-1.5",
                            },
                            {
                                "name": {"value": "Boston Red Sox"},
                                "americanOdds": "-170",
                                "odds": 1.59,
                                "attr": "1.5",
                            },
                        ],
                    },
                    {
                        "name": {"value": "Total Runs"},
                        "visibility": "Visible",
                        "results": [
                            {"name": {"value": "Over"}, "americanOdds": "-110", "odds": 1.91, "attr": "8.5"},
                            {"name": {"value": "Under"}, "americanOdds": "-110", "odds": 1.91, "attr": "8.5"},
                        ],
                    },
                ],
            },
            {
                "id": "12346",
                "name": "New York Mets at Atlanta Braves",
                "startDate": "2026-04-03T20:00:00Z",
                "participants": [
                    {"name": {"value": "New York Mets"}},
                    {"name": {"value": "Atlanta Braves"}},
                ],
                "games": [
                    {
                        "name": {"value": "Moneyline"},
                        "visibility": "Visible",
                        "results": [
                            {"name": {"value": "New York Mets"}, "americanOdds": "+150", "odds": 2.50},
                            {"name": {"value": "Atlanta Braves"}, "americanOdds": "-170", "odds": 1.59},
                        ],
                    },
                ],
            },
        ]
    }


class TestParseAmerican:
    def test_positive(self):
        assert _parse_american("+150") == 150

    def test_negative(self):
        assert _parse_american("-170") == -170

    def test_unicode_minus(self):
        assert _parse_american("\u2212250") == -250

    def test_none(self):
        assert _parse_american(None) is None


class TestOddsToAmerican:
    def test_favorite(self):
        assert _odds_to_american(1.5) == -200

    def test_underdog(self):
        assert _odds_to_american(2.5) == 150

    def test_even(self):
        assert _odds_to_american(2.0) == 100

    def test_none(self):
        assert _odds_to_american(None) is None


class TestBetMGMAdapter:
    def setup_method(self):
        self.adapter = BetMGMAdapter()

    def test_supported_sports(self):
        sports = self.adapter.supported_sports()
        assert Sport.MLB in sports
        assert Sport.NBA in sports
        assert Sport.NFL in sports
        assert Sport.NHL in sports
        assert Sport.NCAAF not in sports

    def test_name(self):
        assert self.adapter.name == "betmgm"

    @patch("oddswrap.books.betmgm.cffi_requests.get")
    def test_fetch_moneylines(self, mock_get, mgm_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mgm_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)

        assert len(games) == 2
        padres_game = next(g for g in games if "Padres" in g.away_team)
        assert padres_game.lines[0].away_odds == 102
        assert padres_game.lines[0].home_odds == -120
        assert padres_game.lines[0].book == "betmgm"

    @patch("oddswrap.books.betmgm.cffi_requests.get")
    def test_fetch_spreads(self, mock_get, mgm_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mgm_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_spreads(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].home_spread == 1.5
        assert games[0].lines[0].away_spread == -1.5
        assert games[0].lines[0].home_spread_odds == -170
        assert games[0].lines[0].away_spread_odds == 145

    @patch("oddswrap.books.betmgm.cffi_requests.get")
    def test_fetch_totals(self, mock_get, mgm_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mgm_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_totals(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].total == 8.5
        assert games[0].lines[0].over_odds == -110
        assert games[0].lines[0].under_odds == -110

    @patch("oddswrap.books.betmgm.cffi_requests.get")
    def test_fetch_raw_failure_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []

    def test_unsupported_sport_returns_none(self):
        result = self.adapter._fetch_raw(Sport.NCAAF)
        assert result is None
