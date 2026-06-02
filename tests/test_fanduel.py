"""Tests for the FanDuel adapter using mocked responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from oddswrap.books.fanduel import FanDuelAdapter, _line_from_market_name
from oddswrap.models import Sport, parse_american


class TestLineFromMarketName:
    def test_n_plus(self):
        assert _line_from_market_name("To Record 2+ Hits") == 1.5
        assert _line_from_market_name("To Record 3+ Hits") == 2.5
        assert _line_from_market_name("To Hit 2+ Home Runs") == 1.5

    def test_singular(self):
        assert _line_from_market_name("To Record A Hit") == 0.5
        assert _line_from_market_name("To Hit A Home Run") == 0.5
        assert _line_from_market_name("To Record An RBI") == 0.5

    def test_unknown(self):
        assert _line_from_market_name("Some Weird Market") is None


class TestParseAmerican:
    def test_positive(self):
        assert parse_american("+140") == 140

    def test_negative(self):
        assert parse_american("-165") == -165

    def test_unicode_minus(self):
        assert parse_american("\u2212230") == -230

    def test_none(self):
        assert parse_american(None) is None


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

    @patch("oddswrap.books.fanduel.cffi_requests.get")
    def test_fetch_props(self, mock_get, fd_raw_response):
        """Player props: one PlayerProp per (market, player), Yes-side-only."""
        event_page = {
            "attachments": {
                "markets": {
                    "m1": {
                        "marketName": "To Record 2+ Hits",
                        "runners": [
                            {
                                "runnerName": "Mookie Betts",
                                "isPlayerSelection": True,
                                "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": -110}},
                            },
                            {
                                "runnerName": "Corbin Carroll",
                                "isPlayerSelection": True,
                                "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": 130}},
                            },
                        ],
                    },
                    "m2": {
                        "marketName": "To Hit A Home Run",
                        "runners": [
                            {
                                "runnerName": "Shohei Ohtani",
                                "isPlayerSelection": True,
                                "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": 1000}},
                            }
                        ],
                    },
                    # Non-player market should be ignored
                    "m3": {
                        "marketName": "Moneyline",
                        "runners": [{"runnerName": "Arizona Diamondbacks", "winRunnerOdds": {}}],
                    },
                }
            }
        }

        def side_effect(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "event-page" in url:
                resp.json.return_value = event_page
            else:
                resp.json.return_value = fd_raw_response
            return resp

        mock_get.side_effect = side_effect

        # Without subcategory filter — all player props across both game events
        props = self.adapter.fetch_props(Sport.MLB, category_id="popular")
        # fd_raw_response has 2 game events; each returns 3 player props (2 hits + 1 HR)
        assert len(props) == 6
        assert all(p.under_odds is None for p in props)
        assert {p.market for p in props} == {"To Record 2+ Hits", "To Hit A Home Run"}

        betts = next(p for p in props if p.player == "Mookie Betts")
        assert betts.line == 1.5
        assert betts.over_odds == -110

        ohtani = next(p for p in props if p.player == "Shohei Ohtani")
        assert ohtani.line == 0.5
        assert ohtani.over_odds == 1000

    @patch("oddswrap.books.fanduel.cffi_requests.get")
    def test_fetch_props_subcategory_filter(self, mock_get, fd_raw_response):
        event_page = {
            "attachments": {
                "markets": {
                    "m1": {
                        "marketName": "To Record 2+ Hits",
                        "runners": [
                            {
                                "runnerName": "Mookie Betts",
                                "isPlayerSelection": True,
                                "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": -110}},
                            }
                        ],
                    },
                    "m2": {
                        "marketName": "To Hit A Home Run",
                        "runners": [
                            {
                                "runnerName": "Shohei Ohtani",
                                "isPlayerSelection": True,
                                "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": 1000}},
                            }
                        ],
                    },
                }
            }
        }

        def side_effect(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = event_page if "event-page" in url else fd_raw_response
            return resp

        mock_get.side_effect = side_effect

        props = self.adapter.fetch_props(Sport.MLB, category_id="popular", subcategory_id="To Hit A Home Run")
        assert len(props) == 2  # one per game event
        assert all(p.market == "To Hit A Home Run" for p in props)
        assert all(p.player == "Shohei Ohtani" for p in props)
