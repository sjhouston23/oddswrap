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

    @patch("oddswrap.books.draftkings.cffi_requests.get")
    def test_fetch_props_over_under(self, mock_get):
        """Over/Under prop markets (e.g. Hits O/U) parse into one prop per market."""
        data = {
            "events": [{"id": "e1", "name": "NY Mets @ ATL Braves"}],
            "markets": [{"id": "m1", "eventId": "e1", "name": "Mookie Betts Hits O/U"}],
            "selections": [
                {"marketId": "m1", "label": "Over 1.5", "points": 1.5, "displayOdds": {"american": "+120"}},
                {"marketId": "m1", "label": "Under 1.5", "points": 1.5, "displayOdds": {"american": "-150"}},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = data
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        props = self.adapter.fetch_props(Sport.MLB, category_id="743", subcategory_id="6719")
        assert len(props) == 1
        p = props[0]
        assert p.player == "Mookie Betts Hits O/U"
        assert p.line == 1.5
        assert p.over_odds == 120
        assert p.under_odds == -150

    @patch("oddswrap.books.draftkings.cffi_requests.get")
    def test_fetch_props_x_plus_thresholds(self, mock_get):
        """X+ markets emit one prop per threshold (1+, 2+, 3+), Yes-side-only."""
        data = {
            "events": [{"id": "e1", "name": "NY Mets @ ATL Braves"}],
            "markets": [{"id": "m1", "eventId": "e1", "name": "Aaron Judge Home Runs"}],
            "selections": [
                {"marketId": "m1", "label": "1+", "points": None, "displayOdds": {"american": "+250"}},
                {"marketId": "m1", "label": "2+", "points": None, "displayOdds": {"american": "+900"}},
                {"marketId": "m1", "label": "3+", "points": None, "displayOdds": {"american": "\u22122500"}},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = data
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        props = self.adapter.fetch_props(Sport.MLB, category_id="743", subcategory_id="17319")
        # One prop per threshold — not collapsed
        assert len(props) == 3
        by_line = {p.line: p for p in props}
        assert set(by_line) == {0.5, 1.5, 2.5}
        # 1+ → line 0.5, Yes-side-only
        assert by_line[0.5].over_odds == 250
        assert by_line[0.5].under_odds is None
        # 2+ → line 1.5
        assert by_line[1.5].over_odds == 900
        # 3+ → line 2.5, unicode-minus odds parsed
        assert by_line[2.5].over_odds == -2500
        assert all(p.player == "Aaron Judge Home Runs" for p in props)

    @patch("oddswrap.books.draftkings.cffi_requests.get")
    def test_fetch_props_mixed_markets(self, mock_get):
        """A payload with both O/U and X+ markets flows both through correctly."""
        data = {
            "events": [{"id": "e1", "name": "NY Mets @ ATL Braves"}],
            "markets": [
                {"id": "m1", "eventId": "e1", "name": "Player A Hits O/U"},
                {"id": "m2", "eventId": "e1", "name": "Player B Hits"},
            ],
            "selections": [
                {"marketId": "m1", "label": "Over 0.5", "points": 0.5, "displayOdds": {"american": "-200"}},
                {"marketId": "m1", "label": "Under 0.5", "points": 0.5, "displayOdds": {"american": "+160"}},
                {"marketId": "m2", "label": "1+", "points": None, "displayOdds": {"american": "-180"}},
                {"marketId": "m2", "label": "2+", "points": None, "displayOdds": {"american": "+210"}},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = data
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        props = self.adapter.fetch_props(Sport.MLB, category_id="743", subcategory_id="x")
        # 1 O/U prop + 2 threshold props = 3
        assert len(props) == 3
        ou = [p for p in props if p.player == "Player A Hits O/U"]
        assert len(ou) == 1 and ou[0].under_odds == 160
        thresholds = [p for p in props if p.player == "Player B Hits"]
        assert len(thresholds) == 2
        assert all(p.under_odds is None for p in thresholds)
