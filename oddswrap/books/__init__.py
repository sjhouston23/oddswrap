"""Sportsbook adapters."""

from oddswrap.books.bovada import BovadaAdapter
from oddswrap.books.draftkings import DraftKingsAdapter
from oddswrap.books.fanduel import FanDuelAdapter

__all__ = ["BovadaAdapter", "DraftKingsAdapter", "FanDuelAdapter"]
