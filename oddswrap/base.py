"""Base class for sportsbook adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from oddswrap.models import Game, Sport


class BookAdapter(ABC):
    """Base class all sportsbook adapters must implement.

    Each market type has its own method. Adapters should implement
    the markets they support and leave the rest raising NotImplementedError
    (the client handles this gracefully).
    """

    name: str = "base"

    @abstractmethod
    def supported_sports(self) -> List[Sport]:
        """Return list of sports this adapter supports."""
        ...

    def fetch_moneylines(self, sport: Sport) -> List[Game]:
        """Fetch moneyline (h2h) odds. Populates Line.home_odds / away_odds."""
        raise NotImplementedError(f"{self.name} does not support moneylines for {sport}")

    def fetch_spreads(self, sport: Sport) -> List[Game]:
        """Fetch spread/run-line odds. Populates Line spread fields."""
        raise NotImplementedError(f"{self.name} does not support spreads for {sport}")

    def fetch_totals(self, sport: Sport) -> List[Game]:
        """Fetch over/under totals. Populates Line.total / over_odds / under_odds."""
        raise NotImplementedError(f"{self.name} does not support totals for {sport}")
