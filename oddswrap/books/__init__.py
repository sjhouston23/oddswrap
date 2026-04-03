"""Sportsbook adapters."""
from oddswrap.books.draftkings import DraftKingsAdapter
from oddswrap.books.fanduel import FanDuelAdapter

__all__ = ["DraftKingsAdapter", "FanDuelAdapter"]
