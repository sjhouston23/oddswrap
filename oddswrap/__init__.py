"""oddswrap — Unified Python SDK for sportsbook odds.

Usage:
    from oddswrap import OddsClient

    client = OddsClient()
    games = client.get_odds(sport="mlb")

    for game in games:
        print(f"{game.away_team} @ {game.home_team}")
        for line in game.lines:
            print(f"  {line.book}: {line.home_odds}/{line.away_odds}")
"""

from oddswrap.client import OddsClient
from oddswrap.models import Game, Line, PlayerProp, PropCategory, Sport
from oddswrap.normalize import normalize_team

__all__ = ["Game", "Line", "OddsClient", "PlayerProp", "PropCategory", "Sport", "normalize_team"]
__version__ = "1.2.0"
