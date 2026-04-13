"""Sportsbook adapters."""

from oddswrap.books.betmgm import BetMGMAdapter
from oddswrap.books.betrivers import BetRiversAdapter
from oddswrap.books.bovada import BovadaAdapter
from oddswrap.books.caesars import CaesarsAdapter
from oddswrap.books.draftkings import DraftKingsAdapter
from oddswrap.books.fanduel import FanDuelAdapter

__all__ = [
    "BetMGMAdapter",
    "BetRiversAdapter",
    "BovadaAdapter",
    "CaesarsAdapter",
    "DraftKingsAdapter",
    "FanDuelAdapter",
]
