# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**oddswrap** is a standalone Python SDK for fetching sportsbook odds directly from sportsbook APIs. It wraps DraftKings, FanDuel, Bovada, BetRivers (Kambi), BetMGM, and Caesars behind a unified interface with standardized input/output. It covers game-line markets (moneylines, spreads/run-lines, totals) and player props. No API keys, no middleman services — goes direct to the source using `curl_cffi` for TLS fingerprint impersonation.

## Architecture

```
oddswrap/
  __init__.py          # Public exports: OddsClient, Game, Line, Sport, PlayerProp, PropCategory, normalize_team
  client.py            # OddsClient — parallel fetch from all books, merge by game
  models.py            # Dataclasses: Game, Line, PlayerProp, PropCategory; enums: Sport, Market
  base.py              # BookAdapter ABC — interface all book adapters implement
  normalize.py         # Team name normalization across books (MLB/NBA/NFL/NHL aliases)
  books/
    __init__.py         # Re-exports all adapters
    betmgm.py           # BetMGM CDS API adapter (bwin/Entain)
    betrivers.py        # BetRivers adapter (Kambi platform, parameterizable)
    bovada.py           # Bovada coupon API adapter
    caesars.py          # Caesars (americanwagering.com) adapter
    draftkings.py       # DraftKings sportscontent API adapter
    fanduel.py          # FanDuel sbapi adapter
tests/
  conftest.py          # Shared fixtures with mock API responses
  test_models.py       # Tests for Game, Line, Sport, odds conversion
  test_normalize.py    # Tests for team name normalization
  test_betmgm.py       # Tests for BetMGM adapter (mocked HTTP)
  test_betrivers.py    # Tests for BetRivers adapter (mocked HTTP)
  test_bovada.py       # Tests for Bovada adapter (mocked HTTP)
  test_caesars.py      # Tests for Caesars adapter (mocked HTTP)
  test_draftkings.py   # Tests for DraftKings adapter (mocked HTTP)
  test_fanduel.py      # Tests for FanDuel adapter (mocked HTTP)
  test_client.py       # Tests for OddsClient merge/filter logic
.github/workflows/
  ci.yml               # Lint + test on push/PR
  release.yml          # Auto version bump + changelog + GitHub release
```

## Key Design Decisions

- **Standalone package** — no external app dependencies. Can be used by any Python project.
- **`curl_cffi` with `impersonate="chrome120"`** — both DraftKings and FanDuel block standard HTTP clients via Cloudflare/TLS fingerprinting. `curl_cffi` impersonates a real browser's TLS handshake.
- **Market-specific methods** — `get_moneylines()`, `get_spreads()`, `get_totals()`, `get_all()` instead of a vague `get_odds()`. Each returns `List[Game]` with the relevant `Line` fields populated. Player props are exposed via `get_prop_categories()` (discover available prop markets) and `get_props(sport, category_id, subcategory_id=None, book=None)` → `List[PlayerProp]`. Helper introspection: `OddsClient.available_books` and `OddsClient.supports(sport)`.
- **Automatic team name normalization** — DraftKings uses abbreviations ("NY Mets"), FanDuel uses full names ("New York Mets"). The `normalize.py` module maps both to canonical lowercase forms for cross-book merging.
- **Parallel fetching** — `OddsClient` fetches from all adapters concurrently via `ThreadPoolExecutor`.
- **Adapter pattern** — each sportsbook is a `BookAdapter` subclass. Adding a new book means implementing `fetch_moneylines()`, `fetch_spreads()`, `fetch_totals()` for the sports it supports, and optionally `fetch_prop_categories()` / `fetch_props()` for player props. The game-line `fetch_*` methods default to raising `NotImplementedError` (handled gracefully by the client); the prop methods default to returning `[]`.
- **Sport coverage** — the `Sport` enum has `MLB, NBA, NFL, NHL, NCAAF, NCAAB`. Most adapters declare only MLB/NBA/NFL/NHL via `supported_sports()`; Bovada additionally supports NCAAF/NCAAB.
- **Player props** — DraftKings, FanDuel, Bovada, and BetRivers implement props (`fetch_prop_categories`/`fetch_props`). BetMGM and Caesars currently do game lines only (they inherit the no-op prop defaults).

## Sportsbook API Details

### DraftKings

**Endpoint:** `https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1/leagues/{league_id}/categories/{category_id}`

**League IDs:** MLB=84240, NBA=42648, NFL=88808, NHL=42133  
**Category 493** = Full Game lines (moneylines, spreads, totals all in one response)

**Response structure:**
```json
{
  "events": [{"id": "123", "name": "TOR Blue Jays @ CHI White Sox", "startDate": "..."}],
  "markets": [{"id": "m1", "name": "Moneyline", "eventId": "123"}],
  "selections": [{"marketId": "m1", "label": "TOR Blue Jays", "displayOdds": {"american": "+150"}, "points": null}]
}
```

- Events contain the matchup name and start time
- Markets link to events and identify the market type ("Moneyline", "Run Line", "Total")
- Selections contain the actual odds, linked to markets

**Team names use abbreviations:** "TOR Blue Jays", "CHI White Sox", "NY Mets", "SF Giants"

### FanDuel

**Endpoint:** `https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page?page=CUSTOM&customPageId={sport}&_ak=FhMFpcPWXMeyZxOx`

**The `_ak` parameter is required** — without it, the API returns 400. This appears to be a static app key embedded in FanDuel's frontend JS.

**Sport page IDs:** mlb, nba, nfl, nhl

**Response structure:**
```json
{
  "attachments": {
    "events": {"35443901": {"name": "San Diego Padres (M King) @ Boston Red Sox (S Gray)", "openDate": "..."}},
    "markets": {"m1": {"marketName": "Moneyline", "eventId": 35443901, "runners": [
      {"runnerName": "San Diego Padres", "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": "+102"}}}
    ]}}
  }
}
```

- Events are keyed by ID, contain matchup name (with pitcher info in parens) and start time
- Markets are keyed by ID, contain `marketName` and nested `runners` array with odds
- Market names: "Moneyline", "Run Line" (MLB spread), "Total Runs" (MLB totals)

**Team names use full names with starters:** "Atlanta Braves (R Lopez)" — the adapter strips the starter info.

**State subdomain:** Uses `nj` but works from any IP. Other states (ny, pa, il, etc.) also work.

### Bovada

**Endpoint:** `https://www.bovada.lv/services/sports/event/coupon/events/A/description/{sport_path}?lang=en`

**Sport paths:** `baseball/mlb`, `basketball/nba`, `football/nfl`, `hockey/nhl`, `football/college-football`, `basketball/college-basketball`

**No authentication required.**

**Response structure:**
```json
[{
  "events": [{
    "id": "...",
    "description": "Team A @ Team B",
    "competitors": [{"name": "Team A", "home": false}, {"name": "Team B", "home": true}],
    "startTime": 1712170800000,
    "displayGroups": [{"description": "Game Lines", "markets": [{
      "description": "Moneyline", "status": "O",
      "outcomes": [{"description": "Team A", "status": "O", "price": {"american": "+150", "handicap": "1.5"}}]
    }]}]
  }]
}]
```

- Response is a JSON array — events in `response[0]["events"]`
- `competitors` array with `home` boolean identifies home/away (no name-splitting needed)
- American odds in `price.american` (string), handicap in `price.handicap` (string)
- `startTime` is epoch milliseconds — adapter converts to ISO 8601
- Status `"O"` = open/active
- Market names: `"Moneyline"`, `"Point Spread"` (or `"Runline"` for MLB), `"Total"`

**Team names use full names:** "New York Mets", "Atlanta Braves" — normalizes cleanly.

### BetRivers (Kambi)

**Endpoint:** `https://eu-offering-api.kambicdn.com/offering/v2018/{operator}/listView/{sport}/{league}/all/all/matches.json?lang=en_US&market=US`

**Operator slugs:** `rsiusnj` (BetRivers NJ, default), `rsiuspa` (PA), `rsiusil` (IL)

**Sport paths:** `baseball/mlb`, `basketball/nba`, `american_football/nfl`, `ice_hockey/nhl`

**No authentication required** — Kambi's CDN API is open.

**Response structure:** Two top-level arrays — `events[]` and `betOffers[]` linked by `eventId`.

- Events have `id`, `homeName`, `awayName`, `start` (ISO 8601)
- BetOffers have `betOfferType.name` ("TWO_WAY", "TWO_WAY_HANDICAP", "OVER_UNDER")
- Outcomes have `label` (team name), `odds` (decimal * 1000), `oddsAmerican` (string), `line` (handicap * 1000), `status` ("OPEN")
- `outcome.type`: "OT_ONE"/"OT_TWO" for match, "OT_OVER"/"OT_UNDER" for totals

**Odds format:** Integer decimal * 1000 (e.g., 2150 = 2.150 decimal). Also provides `oddsAmerican` string.

**Parameterizable:** The adapter accepts `operator` and `display_name` for supporting other Kambi-backed books (Unibet, etc.).

### BetMGM

**Endpoint:** `https://sports.{state}.betmgm.com/cds-api/bettingoffer/fixtures`

**Required params:** `x-bwin-accessid`, `sportIds`, `competitionIds`, `lang=en-us`, `country=US`, `userCountry=US`, `offerMapping=Filtered`, `fixtureTypes=Standard`, `sortBy=StartDate`, `offerCategories=Gridable` (plus `gridGroupId` when drilling into a grid view). Market odds come back in each fixture's `optionMarkets`.

**Access ID:** auto-discovered at runtime from BetMGM's client-config endpoint (`https://www.{state}.betmgm.com/en/api/clientconfig`, parsed out of `msPreloader.groupingUrl`), so it stays current when they rotate the key. Falls back to the hardcoded `_FALLBACK_ACCESS_ID` (`ZTllNjllODUtOWQwNS00YmU4LWE4NTEtZGZjOTkzMGM5OWU4`) if discovery fails.

**Sport IDs:** MLB=23, NBA=7, NFL=11, NHL=12
**Competition IDs:** MLB=75, NBA=6004, NFL=35, NHL=25

**Response structure:** `fixtures[]` array, each with `participants[]`, `games[]` (markets), and `results[]`.

- Participants have `name.value` and `properties.type` ("HOME"/"AWAY")
- Games (markets) have `name.value` ("Money Line", "Run Line", "Total Runs"), `visibility` ("Visible")
- Results have `name.value`, `odds` (decimal float), `americanOdds` (string), `attr` (handicap string)

**State subdomain:** Uses `nj` by default. Other states also work.

### Caesars

**Endpoint:** `https://api.americanwagering.com/regions/us/locations/{state}/brands/czr/sb/v3/sports/{sport_id}/events/schedule?competitionIds={comp_id}`

**No authentication required.**

**Sport IDs:** `baseball`, `basketball`, `americanfootball`, `icehockey`

**Competition IDs (UUIDs):**
- MLB: `04f90892-3afa-4e84-acce-5b89f151063d`
- NBA: `5806c896-4eec-4de1-874f-afed93114b8c`
- NFL: `007d7c61-07a7-4e18-bb40-15104b6eac92`
- NHL: `b7b715a9-c7e8-4c47-af0a-77385b525e09`

**Response structure:** `competitions[0].events[]` with inline `markets[]` and `selections[]`.

- Event names use `|at|` delimiter: "New York Mets |at| Atlanta Braves"
- Competitors array with `type` ("HOME"/"AWAY") preferred for team identification
- Market names may use pipe delimiters: `|Moneyline|`, `|Spread|`
- Selections have `price.a` (American string), `price.d` (decimal float)
- Spread line on market object (`market.line`), not on individual selections

**State subdomain:** Uses `nj` by default.

## How to Add a New Sportsbook

1. Create `oddswrap/books/newbook.py`
2. Subclass `BookAdapter`
3. Set `name = "newbook"`
4. Implement `supported_sports()` → list of `Sport` enums
5. Implement `fetch_moneylines(sport)` → `List[Game]`
6. Optionally implement `fetch_spreads()` and `fetch_totals()`
7. Each method should:
   - Make HTTP request(s) using `curl_cffi` with `impersonate="chrome120"`
   - Parse the response into `Game` objects, each with one `Line`
   - Return `List[Game]`
8. Add the adapter to `oddswrap/books/__init__.py`
9. Add it to `_DEFAULT_ADAPTERS` in `client.py` if it should be included by default
10. Add team name aliases to `normalize.py` if the book uses non-standard names

## How to Add a New Sport

1. Add the sport to the `Sport` enum in `models.py`
2. Add the sport's league ID / page ID to each adapter's config dict (e.g., `_LEAGUE_IDS` in draftkings.py)
3. Add team name aliases for the new sport to `normalize.py`
4. Verify market names — some sports use different names (e.g., "Run Line" for MLB vs "Spread" for NBA/NFL)

## Common Commands

```bash
# Install for development (includes ruff, pytest, pre-commit, semantic-release)
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=oddswrap --cov-report=term-missing

# Lint
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Format
ruff format .

# Check formatting (no changes)
ruff format --check .

# Install pre-commit hooks locally
pre-commit install
pre-commit install --hook-type commit-msg

# Quick smoke test
python -c "from oddswrap import OddsClient; print(OddsClient().get_moneylines('mlb'))"
```

## Versioning & Releases

This project uses **Semantic Versioning** and **Conventional Commits** for automated releases.

### Commit Message Format

All commits must follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <description>

[optional body]
```

**Types that trigger version bumps:**
- `fix:` → patch bump (0.1.0 → 0.1.1)
- `perf:` → patch bump
- `feat:` → minor bump (0.1.0 → 0.2.0)
- `BREAKING CHANGE:` in footer or `!` after type → major bump (0.1.0 → 1.0.0)

**Other allowed types** (no version bump): `build`, `chore`, `ci`, `docs`, `refactor`, `style`, `test`

### How Releases Work

1. Merge PR to `main` with conventional commit messages
2. GitHub Actions `release.yml` runs `python-semantic-release`
3. It analyzes commits since last release, determines the version bump
4. Updates `pyproject.toml` version, `oddswrap/__init__.py` `__version__`, and `CHANGELOG.md`
5. Creates a git tag and GitHub Release

### Version is defined in two places (kept in sync automatically):
- `pyproject.toml` → `project.version`
- `oddswrap/__init__.py` → `__version__`

## CI/CD

### CI Workflow (`.github/workflows/ci.yml`)
Runs on every push to `main` and every PR:
- **Lint job**: ruff check + ruff format check
- **Test job**: pytest across Python 3.10, 3.11, 3.12, 3.13
- **Check gate**: blocks merge if any job fails

### Release Workflow (`.github/workflows/release.yml`)
Runs on push to `main` only:
- Analyzes conventional commits to determine version bump
- Updates version in source files
- Updates CHANGELOG.md
- Creates git tag + GitHub Release

## Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:
- Trailing whitespace, end-of-file fixer, YAML/TOML validation
- **ruff** lint (with auto-fix) + format
- **conventional-pre-commit** enforces commit message format on `commit-msg` hook

Install with: `pre-commit install && pre-commit install --hook-type commit-msg`

## Known Limitations

- **Bot detection is fragile** — sportsbooks update their bot detection periodically. If `curl_cffi` impersonation stops working, try updating the `impersonate` version string (e.g., `"chrome124"`, `"chrome130"`).
- **FanDuel `_ak` key** — this is a static key from their frontend JS. If FanDuel rotates it, the adapter will return 400 and need updating.
- **DraftKings league IDs** — these can change between seasons. The current IDs (84240 for MLB, etc.) are for the 2026 season.
- **No rate limiting built in** — the caller is responsible for not hammering the APIs. Both books seem to handle moderate request rates fine (every 30-60 seconds).
- **Unicode minus signs** — DraftKings uses `\u2212` (−) instead of standard `-` for negative odds. The adapters handle this, but be aware if parsing raw responses.
- **Doubleheaders** — games on the same day between the same teams will appear as separate Game entries (same team names, different game_id and start_time).

## Dependencies

**Runtime:**
- `curl_cffi>=0.7` — TLS fingerprint impersonation for accessing sportsbook APIs
- Python 3.10+

**Dev (installed via `pip install -e ".[dev]"`):**
- `pytest>=7.0` + `pytest-cov>=4.0` — testing and coverage
- `ruff>=0.4` — linting and formatting
- `pre-commit>=3.0` — git hook management
- `python-semantic-release>=9.0` — automated versioning and changelog

## Integration with Other Projects

This package is designed to be imported as a dependency:

```python
# In your requirements.txt or pyproject.toml:
# oddswrap @ git+https://github.com/sjhouston23/oddswrap.git

from oddswrap import OddsClient, Game, Line, Sport

client = OddsClient()
games = client.get_moneylines(Sport.MLB)

# Convert to your app's format
for game in games:
    for line in game.lines:
        your_format = {
            "game_id": f"{game.away_team}@{game.home_team}",
            "book": line.book,
            "home_odds": line.home_odds,
            "away_odds": line.away_odds,
        }
```
