"""Tests for the BetRivers (Kambi) adapter using mocked responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from oddswrap.books.betrivers import BetRiversAdapter, _kambi_line, _kambi_odds_to_american
from oddswrap.models import Sport


class TestHelpers:
    def test_kambi_odds_to_american_positive(self):
        # 2.45 decimal = +145
        assert _kambi_odds_to_american({"odds": 2450}) == 145

    def test_kambi_odds_to_american_negative(self):
        # 1.61 decimal = round(-100/0.61) ≈ -164
        result = _kambi_odds_to_american({"odds": 1610})
        assert result is not None
        assert result < 0

    def test_kambi_odds_to_american_even(self):
        # 2.0 decimal = +100
        assert _kambi_odds_to_american({"odds": 2000}) == 100

    def test_kambi_odds_to_american_prefers_american_string(self):
        # oddsAmerican takes precedence
        assert _kambi_odds_to_american({"odds": 2450, "oddsAmerican": "+145"}) == 145

    def test_kambi_odds_to_american_none(self):
        assert _kambi_odds_to_american({"odds": None}) is None
        assert _kambi_odds_to_american({}) is None

    def test_kambi_odds_to_american_invalid(self):
        assert _kambi_odds_to_american({"odds": 1000}) is None
        assert _kambi_odds_to_american({"odds": 500}) is None

    def test_kambi_line_positive(self):
        assert _kambi_line(1500) == 1.5

    def test_kambi_line_negative(self):
        assert _kambi_line(-1500) == -1.5

    def test_kambi_line_total(self):
        assert _kambi_line(8500) == 8.5

    def test_kambi_line_none(self):
        assert _kambi_line(None) is None


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

    def test_custom_operator(self):
        adapter = BetRiversAdapter(operator="rsiuspa", display_name="betrivers_pa")
        assert adapter.name == "betrivers_pa"

    @patch("oddswrap.books.betrivers.cffi_requests.get")
    def test_fetch_moneylines(self, mock_get, betrivers_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = betrivers_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)

        assert len(games) == 2
        mets_game = next(g for g in games if "Mets" in g.away_team)
        assert mets_game.lines[0].book == "betrivers"
        assert mets_game.lines[0].away_odds is not None
        assert mets_game.lines[0].home_odds is not None
        assert mets_game.home_team == "Atlanta Braves"
        assert mets_game.away_team == "New York Mets"

    @patch("oddswrap.books.betrivers.cffi_requests.get")
    def test_fetch_spreads(self, mock_get, betrivers_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = betrivers_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_spreads(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].home_spread == -1.5
        assert games[0].lines[0].away_spread == 1.5
        assert games[0].lines[0].home_spread_odds is not None
        assert games[0].lines[0].away_spread_odds is not None

    @patch("oddswrap.books.betrivers.cffi_requests.get")
    def test_fetch_totals(self, mock_get, betrivers_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = betrivers_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_totals(Sport.MLB)

        assert len(games) == 1
        assert games[0].lines[0].total == 8.5
        assert games[0].lines[0].over_odds is not None
        assert games[0].lines[0].under_odds is not None

    @patch("oddswrap.books.betrivers.cffi_requests.get")
    def test_fetch_raw_failure_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []

    def test_unsupported_sport_returns_none(self):
        result = self.adapter._fetch_raw(Sport.NCAAF)
        assert result is None

    @patch("oddswrap.books.betrivers.cffi_requests.get")
    def test_start_time_from_event(self, mock_get, betrivers_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = betrivers_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games[0].start_time == "2026-04-03T18:00:00Z"

    @patch("oddswrap.books.betrivers.cffi_requests.get")
    def test_game_id_from_event(self, mock_get, betrivers_raw_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = betrivers_raw_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games[0].game_id == "1001"

    @patch("oddswrap.books.betrivers.cffi_requests.get")
    def test_closed_outcomes_skipped(self, mock_get):
        """Outcomes with status != OPEN should be skipped."""
        data = {
            "events": [{"id": 1, "homeName": "Team A", "awayName": "Team B", "start": "2026-04-03T18:00:00Z"}],
            "betOffers": [
                {
                    "eventId": 1,
                    "betOfferType": {"name": "Match"},
                    "outcomes": [
                        {"label": "Team B", "odds": 2000, "status": "CLOSED"},
                        {"label": "Team A", "odds": 1800, "status": "CLOSED"},
                    ],
                }
            ],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = data
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        games = self.adapter.fetch_moneylines(Sport.MLB)
        assert games == []
