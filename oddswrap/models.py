"""Core data models for oddswrap."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Sport(str, Enum):
    MLB = "mlb"
    NBA = "nba"
    NFL = "nfl"
    NHL = "nhl"
    NCAAF = "ncaaf"
    NCAAB = "ncaab"


class Market(str, Enum):
    MONEYLINE = "moneyline"
    SPREAD = "spread"
    TOTAL = "total"


@dataclass
class Line:
    """A single sportsbook's odds for one game."""

    book: str
    home_odds: int | None = None  # American odds (e.g., -150)
    away_odds: int | None = None  # American odds (e.g., +130)
    home_spread: float | None = None
    away_spread: float | None = None
    home_spread_odds: int | None = None
    away_spread_odds: int | None = None
    total: float | None = None
    over_odds: int | None = None
    under_odds: int | None = None
    fetched_at: str | None = None

    @property
    def home_decimal(self) -> float | None:
        return _american_to_decimal(self.home_odds) if self.home_odds is not None else None

    @property
    def away_decimal(self) -> float | None:
        return _american_to_decimal(self.away_odds) if self.away_odds is not None else None

    @property
    def home_implied(self) -> float | None:
        d = self.home_decimal
        return 1.0 / d if d and d > 0 else None

    @property
    def away_implied(self) -> float | None:
        d = self.away_decimal
        return 1.0 / d if d and d > 0 else None


@dataclass
class Game:
    """A single game with odds from one or more sportsbooks."""

    sport: str
    home_team: str
    away_team: str
    start_time: str | None = None  # ISO 8601
    game_id: str | None = None  # External ID from source
    lines: list[Line] = field(default_factory=list)

    def best_home_odds(self) -> Line | None:
        """Return the line with the best (highest) home moneyline odds."""
        candidates = [ln for ln in self.lines if ln.home_odds is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda ln: ln.home_decimal or 0)

    def best_away_odds(self) -> Line | None:
        """Return the line with the best (highest) away moneyline odds."""
        candidates = [ln for ln in self.lines if ln.away_odds is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda ln: ln.away_decimal or 0)

    def to_dict(self) -> dict:
        return {
            "sport": self.sport,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "start_time": self.start_time,
            "game_id": self.game_id,
            "lines": [
                {
                    "book": ln.book,
                    "home_odds": ln.home_odds,
                    "away_odds": ln.away_odds,
                    "fetched_at": ln.fetched_at,
                }
                for ln in self.lines
            ],
        }


def _american_to_decimal(odds: int) -> float:
    if odds > 0:
        return 1 + odds / 100
    return 1 + 100 / abs(odds)
