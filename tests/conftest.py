"""Shared fixtures and mock data for oddswrap tests."""

from __future__ import annotations

import pytest

# ---------- DraftKings mock response ----------


@pytest.fixture()
def dk_raw_response():
    """Minimal DraftKings sportscontent API response."""
    return {
        "events": [
            {
                "id": "evt1",
                "name": "NY Mets @ ATL Braves",
                "startDate": "2026-04-03T18:00:00Z",
            },
            {
                "id": "evt2",
                "name": "SF Giants @ LA Dodgers",
                "startDate": "2026-04-03T20:00:00Z",
            },
        ],
        "markets": [
            {"id": "mkt_ml1", "name": "Moneyline", "eventId": "evt1"},
            {"id": "mkt_ml2", "name": "Moneyline", "eventId": "evt2"},
            {"id": "mkt_sp1", "name": "Run Line", "eventId": "evt1"},
            {"id": "mkt_tot1", "name": "Total", "eventId": "evt1"},
        ],
        "selections": [
            # Moneyline — evt1
            {"marketId": "mkt_ml1", "label": "NY Mets", "displayOdds": {"american": "+150"}, "points": None},
            {"marketId": "mkt_ml1", "label": "ATL Braves", "displayOdds": {"american": "-170"}, "points": None},
            # Moneyline — evt2
            {"marketId": "mkt_ml2", "label": "SF Giants", "displayOdds": {"american": "+200"}, "points": None},
            {"marketId": "mkt_ml2", "label": "LA Dodgers", "displayOdds": {"american": "\u2212250"}, "points": None},
            # Spread — evt1
            {"marketId": "mkt_sp1", "label": "NY Mets +1.5", "displayOdds": {"american": "-130"}, "points": 1.5},
            {"marketId": "mkt_sp1", "label": "ATL Braves -1.5", "displayOdds": {"american": "+110"}, "points": -1.5},
            # Total — evt1
            {"marketId": "mkt_tot1", "label": "Over 8.5", "displayOdds": {"american": "-110"}, "points": 8.5},
            {"marketId": "mkt_tot1", "label": "Under 8.5", "displayOdds": {"american": "-110"}, "points": 8.5},
        ],
    }


# ---------- FanDuel mock response ----------


@pytest.fixture()
def fd_raw_response():
    """Minimal FanDuel sbapi response."""
    return {
        "attachments": {
            "events": {
                "100": {
                    "name": "New York Mets (S Manaea) @ Atlanta Braves (C Sale)",
                    "openDate": "2026-04-03T18:00:00Z",
                },
                "200": {
                    "name": "San Francisco Giants @ Los Angeles Dodgers",
                    "openDate": "2026-04-03T20:00:00Z",
                },
            },
            "markets": {
                "m_ml1": {
                    "marketName": "Moneyline",
                    "eventId": 100,
                    "runners": [
                        {
                            "runnerName": "New York Mets",
                            "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": "+140"}},
                        },
                        {
                            "runnerName": "Atlanta Braves",
                            "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": "-165"}},
                        },
                    ],
                },
                "m_ml2": {
                    "marketName": "Moneyline",
                    "eventId": 200,
                    "runners": [
                        {
                            "runnerName": "San Francisco Giants",
                            "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": "+190"}},
                        },
                        {
                            "runnerName": "Los Angeles Dodgers",
                            "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": "-230"}},
                        },
                    ],
                },
                "m_sp1": {
                    "marketName": "Run Line",
                    "eventId": 100,
                    "runners": [
                        {
                            "runnerName": "New York Mets",
                            "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": "-120"}},
                            "handicap": 1.5,
                        },
                        {
                            "runnerName": "Atlanta Braves",
                            "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": "+100"}},
                            "handicap": -1.5,
                        },
                    ],
                },
                "m_tot1": {
                    "marketName": "Total Runs",
                    "eventId": 100,
                    "runners": [
                        {
                            "runnerName": "Over",
                            "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": "-105"}},
                            "handicap": 8.5,
                        },
                        {
                            "runnerName": "Under",
                            "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": "-115"}},
                            "handicap": 8.5,
                        },
                    ],
                },
            },
        },
    }
