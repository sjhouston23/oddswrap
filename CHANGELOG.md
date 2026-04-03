# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/) and uses
[Conventional Commits](https://www.conventionalcommits.org/) for automatic
version management.

## [0.1.0] - 2026-04-03

### Added

- Initial release of oddswrap SDK
- `OddsClient` with unified interface for fetching odds across sportsbooks
- DraftKings adapter (moneylines, spreads, totals)
- FanDuel adapter (moneylines, spreads, totals)
- Support for MLB, NBA, NFL, NHL
- Team name normalization for cross-book game matching
- Parallel fetching from multiple sportsbooks via `ThreadPoolExecutor`
- `Game` and `Line` dataclasses with odds conversion utilities
- American-to-decimal odds conversion
- Implied probability calculations
