"""Core data models for oddswrap."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


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
    home_odds: Optional[int] = None    # American odds (e.g., -150)
    away_odds: Optional[int] = None    # American odds (e.g., +130)
    home_spread: Optional[float] = None
    away_spread: Optional[float] = None
    home_spread_odds: Optional[int] = None
    away_spread_odds: Optional[int] = None
    total: Optional[float] = None
    over_odds: Optional[int] = None
    under_odds: Optional[int] = None
    fetched_at: Optional[str] = None

    @property
    def home_decimal(self) -> Optional[float]:
        return _american_to_decimal(self.home_odds) if self.home_odds is not None else None

    @property
    def away_decimal(self) -> Optional[float]:
        return _american_to_decimal(self.away_odds) if self.away_odds is not None else None

    @property
    def home_implied(self) -> Optional[float]:
        d = self.home_decimal
        return 1.0 / d if d and d > 0 else None

    @property
    def away_implied(self) -> Optional[float]:
        d = self.away_decimal
        return 1.0 / d if d and d > 0 else None


@dataclass
class Game:
    """A single game with odds from one or more sportsbooks."""
    sport: str
    home_team: str
    away_team: str
    start_time: Optional[str] = None   # ISO 8601
    game_id: Optional[str] = None      # External ID from source
    lines: List[Line] = field(default_factory=list)

    def best_home_odds(self) -> Optional[Line]:
        """Return the line with the best (highest) home moneyline odds."""
        candidates = [l for l in self.lines if l.home_odds is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda l: l.home_decimal or 0)

    def best_away_odds(self) -> Optional[Line]:
        """Return the line with the best (highest) away moneyline odds."""
        candidates = [l for l in self.lines if l.away_odds is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda l: l.away_decimal or 0)

    def to_dict(self) -> dict:
        return {
            "sport": self.sport,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "start_time": self.start_time,
            "game_id": self.game_id,
            "lines": [
                {
                    "book": l.book,
                    "home_odds": l.home_odds,
                    "away_odds": l.away_odds,
                    "fetched_at": l.fetched_at,
                }
                for l in self.lines
            ],
        }


def _american_to_decimal(odds: int) -> float:
    if odds > 0:
        return 1 + odds / 100
    return 1 + 100 / abs(odds)
