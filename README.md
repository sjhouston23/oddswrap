# oddswrap

Unified Python SDK for fetching sportsbook odds across multiple books and sports. Goes direct to sportsbook APIs — no middleman services, no API keys.

## Installation

```bash
pip install git+https://github.com/sjhouston23/oddswrap.git
```

Or for development:
```bash
git clone https://github.com/sjhouston23/oddswrap.git
cd oddswrap
pip install -e .
```

**Dependency:** `curl_cffi` (handles TLS fingerprinting to access sportsbook APIs)

## Quick Start

```python
from oddswrap import OddsClient

client = OddsClient()
games = client.get_moneylines("mlb")

for game in games:
    tag = " [LIVE]" if game.live else ""
    print(f"{game.away_team} @ {game.home_team}{tag}")
    for line in game.lines:
        print(f"  {line.book}: {line.away_odds}/{line.home_odds}")
    best = game.best_home_odds()
    if best:
        print(f"  Best home: {best.home_odds} @ {best.book}")
```

## API Reference

### OddsClient

```python
from oddswrap import OddsClient

# All registered books
client = OddsClient()

# Specific books only
client = OddsClient(books=["draftkings", "fanduel", "bovada"])

# Custom adapters
from oddswrap.books import DraftKingsAdapter
client = OddsClient(adapters=[DraftKingsAdapter()])
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_moneylines(sport)` | `List[Game]` | Moneyline (h2h/win) odds. `Line.home_odds` and `Line.away_odds` populated. |
| `get_spreads(sport)` | `List[Game]` | Point spread / run line odds. `Line.home_spread`, `away_spread`, `home_spread_odds`, `away_spread_odds` populated. |
| `get_totals(sport)` | `List[Game]` | Over/under totals. `Line.total`, `over_odds`, `under_odds` populated. |
| `get_all(sport)` | `List[Game]` | All markets merged. Each game may have multiple Lines with different fields populated. |
| `available_books` | `List[str]` | Names of all registered adapters. |
| `supports(sport)` | `List[str]` | Book names that support a given sport. |

**`sport` parameter:** Accepts `"mlb"`, `"nba"`, `"nfl"`, `"nhl"` (string) or `Sport` enum.

#### Player Props

```python
# Discover available prop categories from a specific book
cats = client.get_prop_categories("mlb", book="draftkings")
# → [PropCategory(book="draftkings", category_id="743", category_name="Batter Props",
#     subcategory_id="6719", subcategory_name="Hits O/U"), ...]

# Fetch props (DraftKings)
props = client.get_props("mlb", category_id="743", subcategory_id="6719", book="draftkings")

# Fetch props (Bovada)
props = client.get_props("mlb", category_id="Player Props", subcategory_id="Total Hits", book="bovada")

# Fetch props (BetRivers)
props = client.get_props("mlb", category_id="Player Occurrence Line",
    subcategory_id="Total Hits by the Player - Including Extra Innings ...", book="betrivers")

# Fetch props (FanDuel) — player props live under the "popular" tab,
# one market per threshold ("To Record 2+ Hits", "To Hit A Home Run", ...)
props = client.get_props("mlb", category_id="popular", subcategory_id="To Record 2+ Hits", book="fanduel")
```

| Method | Returns | Description |
|--------|---------|-------------|
| `get_prop_categories(sport, book=)` | `List[PropCategory]` | Discover available prop categories. Pass `book` to query a single adapter. |
| `get_props(sport, category_id, subcategory_id=, book=)` | `List[PlayerProp]` | Fetch player props for a category. IDs are book-specific — use `get_prop_categories` to discover them. |

> **Note:** Category and subcategory IDs are book-specific. Use `get_prop_categories()` to discover what each book offers, then pass those IDs to `get_props()`. Props are not merged across books — each `PlayerProp` includes a `book` field.

**"X+" / Yes-only markets.** Threshold markets (DraftKings "1+/2+/3+ Hits", FanDuel "To Record 2+ Hits", "To Hit A Home Run") are mapped onto the standard O/U fields: each threshold becomes its own `PlayerProp` with `over_odds` set, `under_odds=None`, and `line = N - 0.5` (so "2+ hits" → `line=1.5`, "1+"/"A" → `line=0.5`). Filter the "1+" side with `p.line == 0.5`. Because these are Yes-side-only, `1 / decimal(over_odds)` is the break-even (vig-inclusive) probability.

### Game

```python
@dataclass
class Game:
    sport: str                          # e.g., "mlb"
    home_team: str                      # Normalized name, e.g., "new york yankees"
    away_team: str                      # Normalized name
    start_time: Optional[str]           # ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ)
    game_id: Optional[str]              # Source-specific event ID
    live: bool                          # True if the game is currently in progress
    lines: List[Line]                   # One Line per sportsbook (per market)
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `best_home_odds()` | `Line \| None` | Line with highest home moneyline decimal odds. |
| `best_away_odds()` | `Line \| None` | Line with highest away moneyline decimal odds. |
| `to_dict()` | `dict` | Serializable dictionary representation. |

### Line

```python
@dataclass
class Line:
    book: str                               # e.g., "draftkings"

    # Moneyline
    home_odds: Optional[int]                # American odds, e.g., -150
    away_odds: Optional[int]                # American odds, e.g., +130

    # Spread / Run Line
    home_spread: Optional[float]            # e.g., -1.5
    away_spread: Optional[float]            # e.g., +1.5
    home_spread_odds: Optional[int]         # American odds on the spread
    away_spread_odds: Optional[int]

    # Totals (Over/Under)
    total: Optional[float]                  # e.g., 8.5
    over_odds: Optional[int]                # American odds
    under_odds: Optional[int]

    fetched_at: Optional[str]               # ISO 8601 timestamp
```

#### Computed Properties

| Property | Type | Description |
|----------|------|-------------|
| `home_decimal` | `float \| None` | American → decimal conversion |
| `away_decimal` | `float \| None` | American → decimal conversion |
| `home_implied` | `float \| None` | Implied probability (1/decimal) |
| `away_implied` | `float \| None` | Implied probability (1/decimal) |

### PlayerProp

```python
@dataclass
class PlayerProp:
    book: str                           # e.g., "draftkings"
    player: str                         # e.g., "Bobby Witt Jr."
    market: str                         # e.g., "Hits O/U", "Total Hits"
    line: Optional[float]               # e.g., 1.5
    over_odds: Optional[int]            # American odds
    under_odds: Optional[int]           # American odds
    game: Optional[str]                 # e.g., "KC Royals @ DET Tigers"
    event_id: Optional[str]             # Source-specific event ID
    fetched_at: Optional[str]           # ISO 8601 timestamp
```

### PropCategory

```python
@dataclass
class PropCategory:
    book: str                           # e.g., "draftkings"
    category_id: str                    # e.g., "743"
    category_name: str                  # e.g., "Batter Props"
    subcategory_id: Optional[str]       # e.g., "6719"
    subcategory_name: Optional[str]     # e.g., "Hits O/U"
```

### Sport Enum

```python
from oddswrap import Sport

Sport.MLB    # "mlb"
Sport.NBA    # "nba"
Sport.NFL    # "nfl"
Sport.NHL    # "nhl"
Sport.NCAAF  # "ncaaf"
Sport.NCAAB  # "ncaab"
```

### Team Name Normalization

Team names are automatically normalized across all six books when merging:
- DraftKings: `"NY Mets"` → `"new york mets"`
- FanDuel: `"New York Mets (S Gray)"` → `"new york mets"`
- Bovada: `"New York Mets"` → `"new york mets"`
- Caesars: `"New York Mets"` → `"new york mets"`

```python
from oddswrap import normalize_team

normalize_team("NY Mets")       # "new york mets"
normalize_team("ATL Braves")    # "atlanta braves"
normalize_team("Chi White Sox") # "chicago white sox"
```

## Supported Books

| Book | Moneylines | Spreads | Totals | Props | Sports |
|------|:----------:|:-------:|:------:|:-----:|--------|
| DraftKings | ✅ | ✅ | ✅ | ✅ | MLB, NBA, NFL, NHL |
| FanDuel | ✅ | ✅ | ✅ | ✅ | MLB, NBA, NFL, NHL |
| Bovada | ✅ | ✅ | ✅ | ✅ | MLB, NBA, NFL, NHL, NCAAF, NCAAB |
| BetRivers | ✅ | ✅ | ✅ | ✅ | MLB, NBA, NFL, NHL |
| BetMGM | ✅ | ✅ | ✅ | | MLB, NBA, NFL, NHL |
| Caesars | ✅ | ✅ | ✅ | | MLB, NBA, NFL, NHL |

## Adding a New Sportsbook

Create a new adapter in `oddswrap/books/`:

```python
from oddswrap.base import BookAdapter
from oddswrap.models import Game, Line, Sport

class PointsBetAdapter(BookAdapter):
    name = "pointsbet"

    def supported_sports(self):
        return [Sport.MLB, Sport.NBA, Sport.NFL, Sport.NHL]

    def fetch_moneylines(self, sport: Sport) -> list[Game]:
        # Fetch from PointsBet API, parse, return list of Game objects
        ...

    def fetch_spreads(self, sport: Sport) -> list[Game]:
        ...

    def fetch_totals(self, sport: Sport) -> list[Game]:
        ...
```

Then register it:
```python
from oddswrap import OddsClient
from oddswrap.books.pointsbet import PointsBetAdapter

client = OddsClient(adapters=[PointsBetAdapter()])
```

## Architecture

```
oddswrap/
  __init__.py          # Public API: OddsClient, Game, Line, Sport, normalize_team
  client.py            # Unified client — parallel fetch, merge by game
  models.py            # Game, Line, Sport, Market dataclasses
  base.py              # BookAdapter abstract base class
  normalize.py         # Cross-book team name normalization (MLB/NBA/NFL/NHL)
  books/
    __init__.py
    betmgm.py          # BetMGM CDS API (bwin/Entain)
    betrivers.py       # BetRivers / Kambi platform
    bovada.py          # Bovada coupon API
    caesars.py         # Caesars (americanwagering.com)
    draftkings.py      # DraftKings sportscontent API
    fanduel.py         # FanDuel sbapi
```

## How It Works

1. Each sportsbook adapter implements `BookAdapter` with market-specific methods
2. Adapters use `curl_cffi` with browser TLS impersonation to bypass bot detection
3. `OddsClient` calls all six adapters in parallel via `ThreadPoolExecutor`
4. Results are merged by normalized team names so "NY Mets" (DK) matches "New York Mets" (FD/Bovada/Caesars)
5. Each `Game` object aggregates `Line` entries from all books that have odds for that matchup

## License

MIT
