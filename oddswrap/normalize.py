"""Team name normalization for cross-book matching."""

from __future__ import annotations

# Maps known aliases/abbreviations → canonical lowercase name
# Covers MLB, NBA, NFL, NHL
_ALIASES: dict[str, str] = {
    # MLB
    "ari diamondbacks": "arizona diamondbacks",
    "atl braves": "atlanta braves",
    "bal orioles": "baltimore orioles",
    "bos red sox": "boston red sox",
    "chi cubs": "chicago cubs",
    "chi white sox": "chicago white sox",
    "cin reds": "cincinnati reds",
    "cle guardians": "cleveland guardians",
    "col rockies": "colorado rockies",
    "det tigers": "detroit tigers",
    "hou astros": "houston astros",
    "kc royals": "kansas city royals",
    "la angels": "los angeles angels",
    "la dodgers": "los angeles dodgers",
    "laa angels": "los angeles angels",
    "lad dodgers": "los angeles dodgers",
    "mia marlins": "miami marlins",
    "mil brewers": "milwaukee brewers",
    "min twins": "minnesota twins",
    "ny mets": "new york mets",
    "ny yankees": "new york yankees",
    "nym mets": "new york mets",
    "nyy yankees": "new york yankees",
    "oak athletics": "oakland athletics",
    "athletics": "oakland athletics",
    "phi phillies": "philadelphia phillies",
    "pit pirates": "pittsburgh pirates",
    "sd padres": "san diego padres",
    "sf giants": "san francisco giants",
    "sea mariners": "seattle mariners",
    "stl cardinals": "st. louis cardinals",
    "st louis cardinals": "st. louis cardinals",
    "tb rays": "tampa bay rays",
    "tex rangers": "texas rangers",
    "tor blue jays": "toronto blue jays",
    "was nationals": "washington nationals",
    "wsh nationals": "washington nationals",
    # NBA
    "gs warriors": "golden state warriors",
    "gsw warriors": "golden state warriors",
    "sa spurs": "san antonio spurs",
    "no pelicans": "new orleans pelicans",
    "nop pelicans": "new orleans pelicans",
    "ny knicks": "new york knicks",
    "nyk knicks": "new york knicks",
    "bkn nets": "brooklyn nets",
    "bk nets": "brooklyn nets",
    "okc thunder": "oklahoma city thunder",
    "por trail blazers": "portland trail blazers",
    "la lakers": "los angeles lakers",
    "la clippers": "los angeles clippers",
    "lal lakers": "los angeles lakers",
    "lac clippers": "los angeles clippers",
    # NFL
    "gb packers": "green bay packers",
    "ne patriots": "new england patriots",
    "no saints": "new orleans saints",
    "sf 49ers": "san francisco 49ers",
    "tb buccaneers": "tampa bay buccaneers",
    "kc chiefs": "kansas city chiefs",
    "la rams": "los angeles rams",
    "la chargers": "los angeles chargers",
    "lar rams": "los angeles rams",
    "lac chargers": "los angeles chargers",
    "lv raiders": "las vegas raiders",
    "jax jaguars": "jacksonville jaguars",
    # NHL
    "nj devils": "new jersey devils",
    "ny rangers": "new york rangers",
    "ny islanders": "new york islanders",
    "nyr rangers": "new york rangers",
    "nyi islanders": "new york islanders",
    "tb lightning": "tampa bay lightning",
    "la kings": "los angeles kings",
    "sj sharks": "san jose sharks",
    "cb blue jackets": "columbus blue jackets",
    "cbj blue jackets": "columbus blue jackets",
    "stl blues": "st. louis blues",
    "st louis blues": "st. louis blues",
}


def normalize_team(name: str) -> str:
    """Normalize a team name to a canonical lowercase form.

    Handles abbreviations (e.g., 'NY Mets' → 'new york mets'),
    city variants, and common aliases across MLB, NBA, NFL, NHL.
    """
    n = name.strip().lower()
    return _ALIASES.get(n, n)
