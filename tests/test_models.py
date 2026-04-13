"""Tests for oddswrap.models."""

from oddswrap.models import Game, Line, Market, Sport, _american_to_decimal, decimal_to_american


class TestDecimalToAmerican:
    def test_positive_american(self):
        # 2.50 → +150
        assert decimal_to_american(2.50) == 150

    def test_negative_american(self):
        # 1.50 → -200
        assert decimal_to_american(1.50) == -200

    def test_even_money(self):
        # 2.00 → +100
        assert decimal_to_american(2.00) == 100

    def test_heavy_favorite(self):
        # 1.10 → -1000
        assert decimal_to_american(1.10) == -1000

    def test_big_underdog(self):
        # 6.00 → +500
        assert decimal_to_american(6.00) == 500

    def test_invalid_returns_none(self):
        assert decimal_to_american(1.0) is None
        assert decimal_to_american(0.5) is None

    def test_roundtrip_with_american_to_decimal(self):
        # +150 → 2.5 → +150
        dec = _american_to_decimal(150)
        assert decimal_to_american(dec) == 150
        # -200 → 1.5 → -200
        dec = _american_to_decimal(-200)
        assert decimal_to_american(dec) == -200


class TestAmericanToDecimal:
    def test_positive_odds(self):
        assert _american_to_decimal(150) == 2.5

    def test_negative_odds(self):
        assert _american_to_decimal(-200) == 1.5

    def test_even_odds(self):
        assert _american_to_decimal(100) == 2.0

    def test_large_underdog(self):
        assert _american_to_decimal(500) == 6.0


class TestLine:
    def test_decimal_conversion(self):
        line = Line(book="test", home_odds=-150, away_odds=130)
        assert round(line.home_decimal, 4) == round(1 + 100 / 150, 4)
        assert line.away_decimal == 2.3

    def test_implied_probability(self):
        line = Line(book="test", home_odds=-200, away_odds=200)
        assert round(line.home_implied, 4) == round(1 / 1.5, 4)
        assert round(line.away_implied, 4) == round(1 / 3.0, 4)

    def test_none_odds_return_none(self):
        line = Line(book="test")
        assert line.home_decimal is None
        assert line.away_decimal is None
        assert line.home_implied is None
        assert line.away_implied is None


class TestGame:
    def test_best_home_odds(self):
        game = Game(
            sport="mlb",
            home_team="braves",
            away_team="mets",
            lines=[
                Line(book="dk", home_odds=-170),
                Line(book="fd", home_odds=-165),
            ],
        )
        best = game.best_home_odds()
        assert best.book == "fd"  # -165 is better than -170

    def test_best_away_odds(self):
        game = Game(
            sport="mlb",
            home_team="braves",
            away_team="mets",
            lines=[
                Line(book="dk", away_odds=150),
                Line(book="fd", away_odds=140),
            ],
        )
        best = game.best_away_odds()
        assert best.book == "dk"  # +150 is better than +140

    def test_best_odds_no_candidates(self):
        game = Game(sport="mlb", home_team="a", away_team="b", lines=[])
        assert game.best_home_odds() is None
        assert game.best_away_odds() is None

    def test_to_dict(self):
        game = Game(
            sport="mlb",
            home_team="braves",
            away_team="mets",
            start_time="2026-04-03T18:00:00Z",
            game_id="123",
            lines=[Line(book="dk", home_odds=-170, away_odds=150, fetched_at="now")],
        )
        d = game.to_dict()
        assert d["sport"] == "mlb"
        assert d["home_team"] == "braves"
        assert len(d["lines"]) == 1
        assert d["lines"][0]["book"] == "dk"


class TestSportEnum:
    def test_string_value(self):
        assert Sport.MLB.value == "mlb"
        assert Sport("nba") == Sport.NBA

    def test_market_enum(self):
        assert Market.MONEYLINE.value == "moneyline"
