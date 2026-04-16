"""Core data models for oddswrap."""

from __future__ import annotations

import re
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
    start_time: str | None = None  # ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)
    game_id: str | None = None  # External ID from source
    live: bool = False  # True if the game is currently in progress
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
            "live": self.live,
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


@dataclass
class PropCategory:
    """A category of player props available from a sportsbook."""

    book: str
    category_id: str
    category_name: str
    subcategory_id: str | None = None
    subcategory_name: str | None = None


@dataclass
class PlayerProp:
    """A single player prop line from a sportsbook."""

    book: str
    player: str
    market: str  # e.g., "Hits O/U", "Total Hits"
    line: float | None = None  # e.g., 1.5
    over_odds: int | None = None  # American odds
    under_odds: int | None = None  # American odds
    game: str | None = None  # e.g., "KC Royals @ DET Tigers"
    event_id: str | None = None
    fetched_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "book": self.book,
            "player": self.player,
            "market": self.market,
            "line": self.line,
            "over_odds": self.over_odds,
            "under_odds": self.under_odds,
            "game": self.game,
            "event_id": self.event_id,
            "fetched_at": self.fetched_at,
        }


def parse_american(val) -> int | None:
    """Parse American odds from string or int, handling unicode minus (U+2212)."""
    if val is None:
        return None
    try:
        return int(str(val).replace("\u2212", "-"))
    except (ValueError, TypeError):
        return None


def decimal_to_american(decimal_odds: float) -> int | None:
    """Convert decimal odds to American odds.

    - Decimal >= 2.0 → positive American (e.g., 2.50 → +150)
    - Decimal < 2.0 → negative American (e.g., 1.50 → -200)
    - Decimal <= 1.0 → None (invalid)
    """
    if decimal_odds <= 1.0:
        return None
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1) * 100)
    return round(-100 / (decimal_odds - 1))


def normalize_start_time(raw: str | None) -> str | None:
    """Normalize any ISO 8601 variant to ``YYYY-MM-DDTHH:MM:SSZ``.

    Handles: trailing fractional seconds, ``+00:00`` offset, bare ``Z``, etc.
    """
    if raw is None:
        return None
    # Strip fractional seconds (.000, .0000000, etc.)
    s = re.sub(r"\.\d+", "", raw)
    # Normalise "+00:00" offset to "Z"
    s = re.sub(r"\+00:?00$", "Z", s)
    # Ensure trailing Z
    if not s.endswith("Z"):
        s += "Z"
    return s


def _american_to_decimal(odds: int) -> float:
    if odds > 0:
        return 1 + odds / 100
    return 1 + 100 / abs(odds)
