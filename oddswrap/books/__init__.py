"""Sportsbook adapters."""

from oddswrap.books.betmgm import BetMGMAdapter
from oddswrap.books.betrivers import BetRiversAdapter
from oddswrap.books.caesars import CaesarsAdapter
from oddswrap.books.draftkings import DraftKingsAdapter
from oddswrap.books.fanduel import FanDuelAdapter
from oddswrap.books.thescore import TheScoreAdapter

__all__ = [
    "BetMGMAdapter",
    "BetRiversAdapter",
    "CaesarsAdapter",
    "DraftKingsAdapter",
    "FanDuelAdapter",
    "TheScoreAdapter",
]
