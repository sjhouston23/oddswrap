"""Tests for the BetRivers adapter using mocked responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from oddswrap.books.betrivers import BetRiversAdapter, _parse_american
from oddswrap.models import Sport


@pytest.fixture()
def br_listview_response():
    """Minimal Kambi listView response."""
    return {
        "events": [
            {
                "id": 1024785983,
                "name": "SD Padres @ BOS Red Sox",
                "homeName": "Boston Red Sox",
                "awayName": "San Diego Padres",
                "start": "2026-04-03T18:10:00Z",
                "betOffers": [
                    {
                        "betOfferType": {"id": 2, "name": "Match"},
                        "criterion": {"label": "Moneyline"},
                        "outcomes": [
                            {
                                "label": "Boston Red Sox",
                                "odds": 1830,
                                "oddsAmerican": "-121",
                                "participant": "Boston Red Sox",
                            },
                            {
                                "label": "San Diego Padres",
                                "odds": 1970,
                                "oddsAmerican": "-104",
                                "participant": "San Diego Padres",
                            },
                        ],
                    }
                ],
            },
            {
                "id": 1024785928,
                "name": "NY Mets @ SF Giants",
                "homeName": "San Francisco Giants",
                "awayName": "New York Mets",
                "start": "2026-04-03T20:00:00Z",
                "betOffers": [
                    {
                        "betOfferType": {"id": 2, "name": "Match"},
                        "criterion": {"label": "Moneyline"},
                        "outcomes": [
                            {
                                "label": "San Francisco Giants",
                                "odds": 1090,
                                "oddsAmerican": "-1115",
                                "participant": "San Francisco Giants",
                            },
                            {
                                "label": "New York Mets",
                                "odds": 6000,
                                "oddsAmerican": "+500",
                                "participant": "New York Mets",
                            },
                        ],
                    }
                ],
            },
        ],
    }


@pytest.fixture()
def br_betoffer_response():
    """Minimal Kambi betoffer/event response with spread and total."""
    return {
        "betOffers": [
            {
                "betOfferType": {"id": 2, "name": "Match"},
                "criterion": {"label": "Moneyline"},
                "outcomes": [
                    {"label": "Boston Red Sox", "oddsAmerican": "-121"},
                    {"label": "San Diego Padres", "oddsAmerican": "-104"},
                ],
            },
            {
                "betOfferType": {"id": 1, "name": "Handicap"},
                "criterion": {"label": "Run Line"},
                "outcomes": [
                    {"label": "Boston Red Sox", "oddsAmerican": "-210", "line": 1500},
                    {"label": "San Diego Padres", "oddsAmerican": "+160", "line": -1500},
                ],
            },
            {
                "betOfferType": {"id": 6, "name": "Over/Under"},
                "criterion": {"label": "Total Runs"},
                "outcomes": [
                    {"label": "Over", "oddsAmerican": "-115", "line": 8500},
                    {"label": "Under", "oddsAmerican": "-108", "line": 8500},
                ],
            },
        ],
        "events": [
            {
                "id": 1024785983,
                "homeName": "Boston Red Sox",
                "awayName": "San Diego Padres",
            }
        ],
    }


class TestParseAmerican:
    def test_positive(self):
        assert _parse_american("+150") == 150

    def test_negative(self):
        assert _parse_american("-170") == -170

    def test_none(self):
        assert _parse_american(None) is None


class TestBetRiversAdapter:
    def setup_method(self):
        self.adapter = BetRiversAdapter()

    def test_supported_sports(self):
        sports = self.adapter.supported_sports()
        assert Sport.MLB in sports
        assert Sport.NBA in sports
        assert Sport.NFL in sports
        assert Sport.NHL in sports

    def test_name(self):
        assert self.adapter.name == "betrivers"

    @patch("oddswrap.books.betrivers.cffi_requests.get")
    def test_fetch_moneylines(self, mock_get, br_listview_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = br_listview_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)

        assert len(games) == 2
        padres_game = next(g for g in games if "Padres" in g.away_team)
        assert padres_game.lines[0].away_odds == -104
        assert padres_game.lines[0].home_odds == -121
        assert padres_game.lines[0].book == "betrivers"

    @patch("oddswrap.books.betrivers.cffi_requests.get")
    def test_fetch_spreads(self, mock_get, br_listview_response, br_betoffer_response):
        # First call returns listView, second returns betoffer
        mock_resp_list = MagicMock()
        mock_resp_list.json.return_value = br_listview_response
        mock_resp_list.raise_for_status = MagicMock()

        mock_resp_offer = MagicMock()
        mock_resp_offer.json.return_value = br_betoffer_response
        mock_resp_offer.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_resp_list, mock_resp_offer, mock_resp_offer]

        games = self.adapter.fetch_spreads(Sport.MLB)

        assert len(games) >= 1
        game = games[0]
        assert game.lines[0].home_spread == 1.5
        assert game.lines[0].away_spread == -1.5

    @patch("oddswrap.books.betrivers.cffi_requests.get")
    def test_fetch_totals(self, mock_get, br_listview_response, br_betoffer_response):
        mock_resp_list = MagicMock()
        mock_resp_list.json.return_value = br_listview_response
        mock_resp_list.raise_for_status = MagicMock()

        mock_resp_offer = MagicMock()
        mock_resp_offer.json.return_value = br_betoffer_response
        mock_resp_offer.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_resp_list, mock_resp_offer, mock_resp_offer]

        games = self.adapter.fetch_totals(Sport.MLB)

        assert len(games) >= 1
        game = games[0]
        assert game.lines[0].total == 8.5
        assert game.lines[0].over_odds == -115
        assert game.lines[0].under_odds == -108

    @patch("oddswrap.books.betrivers.cffi_requests.get")
    def test_fetch_raw_failure_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []

    def test_unsupported_sport_returns_empty(self):
        result = self.adapter._fetch_events(Sport.NCAAF)
        assert result is None
