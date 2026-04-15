"""Tests for the Caesars adapter using mocked responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from oddswrap.books.caesars import CaesarsAdapter, _clean_name, _parse_handicap, _parse_odds
from oddswrap.models import Sport


class TestHelpers:
    def test_parse_odds_american(self):
        sel = {"price": {"a": "+135", "d": 2.35}}
        assert _parse_odds(sel) == 135

    def test_parse_odds_negative(self):
        sel = {"price": {"a": "-160", "d": 1.63}}
        assert _parse_odds(sel) == -160

    def test_parse_odds_unicode_minus(self):
        sel = {"price": {"a": "\u2212245", "d": 1.41}}
        assert _parse_odds(sel) == -245

    def test_parse_odds_decimal_fallback(self):
        # No American odds, should convert from decimal
        sel = {"price": {"d": 2.50}}
        val = _parse_odds(sel)
        assert val == 150

    def test_parse_odds_empty(self):
        assert _parse_odds({}) is None
        assert _parse_odds({"price": {}}) is None

    def test_parse_handicap(self):
        assert _parse_handicap(1.5) == 1.5
        assert _parse_handicap(-1.5) == -1.5
        assert _parse_handicap("8.5") == 8.5
        assert _parse_handicap(None) is None

    def test_clean_name(self):
        assert _clean_name("|Moneyline|") == "Moneyline"
        assert _clean_name("Moneyline") == "Moneyline"
        assert _clean_name(" |Spread| ") == "Spread"


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
    def test_fetch_moneylines(self, mock_get, caesars_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = caesars_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)

        assert len(games) == 2
        mets_game = next(g for g in games if "Mets" in g.away_team)
        assert mets_game.lines[0].book == "caesars"
        assert mets_game.lines[0].away_odds == 135
        assert mets_game.lines[0].home_odds == -160
        assert mets_game.home_team == "Atlanta Braves"
        assert mets_game.away_team == "New York Mets"

    @patch("oddswrap.books.caesars.cffi_requests.get")
    def test_fetch_moneylines_unicode_minus(self, mock_get, caesars_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = caesars_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        dodgers_game = next(g for g in games if "Dodgers" in g.home_team)
        assert dodgers_game.lines[0].home_odds == -245

    @patch("oddswrap.books.caesars.cffi_requests.get")
    def test_fetch_spreads(self, mock_get, caesars_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = caesars_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_spreads(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].home_spread == -1.5
        assert games[0].lines[0].away_spread == 1.5
        assert games[0].lines[0].home_spread_odds == 110
        assert games[0].lines[0].away_spread_odds == -130

    @patch("oddswrap.books.caesars.cffi_requests.get")
    def test_fetch_totals(self, mock_get, caesars_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = caesars_raw_response
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

    @patch("oddswrap.books.caesars.cffi_requests.get")
    def test_start_time(self, mock_get, caesars_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = caesars_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games[0].start_time == "2026-04-03T18:00:00Z"

    @patch("oddswrap.books.caesars.cffi_requests.get")
    def test_game_id(self, mock_get, caesars_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = caesars_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games[0].game_id == "czr1"

    def test_get_teams_pipe_separator(self):
        """Test parsing team names with |at| separator."""
        event = {"name": "New York Mets |at| Atlanta Braves", "competitors": []}
        result = self.adapter._get_teams(event)
        assert result == ("New York Mets", "Atlanta Braves")

    def test_get_teams_at_separator(self):
        """Test parsing team names with @ separator."""
        event = {"name": "New York Mets @ Atlanta Braves", "competitors": []}
        result = self.adapter._get_teams(event)
        assert result == ("New York Mets", "Atlanta Braves")

    def test_get_teams_competitors_preferred(self):
        """Competitors array takes precedence over name parsing."""
        event = {
            "name": "New York Mets @ Atlanta Braves",
            "competitors": [
                {"name": "NY Mets", "type": "AWAY"},
                {"name": "ATL Braves", "type": "HOME"},
            ],
        }
        result = self.adapter._get_teams(event)
        assert result == ("NY Mets", "ATL Braves")

    @patch("oddswrap.books.caesars.cffi_requests.get")
    def test_inactive_markets_skipped(self, mock_get):
        """Markets with active=False should be skipped."""
        data = {
            "competitions": [
                {
                    "events": [
                        {
                            "id": "e1",
                            "competitors": [
                                {"name": "Team A", "type": "AWAY"},
                                {"name": "Team B", "type": "HOME"},
                            ],
                            "markets": [
                                {
                                    "name": "Moneyline",
                                    "display": True,
                                    "active": False,
                                    "selections": [
                                        {"name": "Team A", "price": {"a": "+100"}},
                                        {"name": "Team B", "price": {"a": "-120"}},
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = data
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []
