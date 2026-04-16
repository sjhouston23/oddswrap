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


# ---------- Bovada mock response ----------


@pytest.fixture()
def bovada_raw_response():
    """Minimal Bovada coupon API response (JSON array with events nested)."""
    return [
        {
            "path": [],
            "events": [
                {
                    "id": "bov1",
                    "description": "NY Mets @ ATL Braves",
                    "startTime": 1712170800000,
                    "competitors": [
                        {"id": "c1", "name": "New York Mets", "home": False},
                        {"id": "c2", "name": "Atlanta Braves", "home": True},
                    ],
                    "displayGroups": [
                        {
                            "description": "Game Lines",
                            "markets": [
                                {
                                    "description": "Moneyline",
                                    "status": "O",
                                    "id": "ml1",
                                    "outcomes": [
                                        {
                                            "description": "New York Mets",
                                            "status": "O",
                                            "price": {"american": "+145", "decimal": "2.45"},
                                        },
                                        {
                                            "description": "Atlanta Braves",
                                            "status": "O",
                                            "price": {"american": "-165", "decimal": "1.61"},
                                        },
                                    ],
                                },
                                {
                                    "description": "Runline",
                                    "status": "O",
                                    "id": "sp1",
                                    "outcomes": [
                                        {
                                            "description": "New York Mets",
                                            "status": "O",
                                            "price": {"american": "-125", "handicap": "1.5"},
                                        },
                                        {
                                            "description": "Atlanta Braves",
                                            "status": "O",
                                            "price": {"american": "+105", "handicap": "-1.5"},
                                        },
                                    ],
                                },
                                {
                                    "description": "Total",
                                    "status": "O",
                                    "id": "tot1",
                                    "outcomes": [
                                        {
                                            "description": "Over",
                                            "status": "O",
                                            "price": {"american": "-108", "handicap": "8.5"},
                                        },
                                        {
                                            "description": "Under",
                                            "status": "O",
                                            "price": {"american": "-112", "handicap": "8.5"},
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                },
                {
                    "id": "bov2",
                    "description": "SF Giants @ LA Dodgers",
                    "startTime": 1712178000000,
                    "competitors": [
                        {"id": "c3", "name": "San Francisco Giants", "home": False},
                        {"id": "c4", "name": "Los Angeles Dodgers", "home": True},
                    ],
                    "displayGroups": [
                        {
                            "description": "Game Lines",
                            "markets": [
                                {
                                    "description": "Moneyline",
                                    "status": "O",
                                    "id": "ml2",
                                    "outcomes": [
                                        {
                                            "description": "San Francisco Giants",
                                            "status": "O",
                                            "price": {"american": "+195", "decimal": "2.95"},
                                        },
                                        {
                                            "description": "Los Angeles Dodgers",
                                            "status": "O",
                                            "price": {"american": "\u2212240", "decimal": "1.42"},
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                },
            ],
        }
    ]


# ---------- BetRivers (Kambi) mock response ----------


@pytest.fixture()
def betrivers_raw_response():
    """Minimal Kambi listView API response (nested wrappers format)."""
    return {
        "events": [
            {
                "event": {
                    "id": 1001,
                    "name": "New York Mets - Atlanta Braves",
                    "homeName": "Atlanta Braves",
                    "awayName": "New York Mets",
                    "start": "2026-04-03T18:00:00Z",
                    "state": "NOT_STARTED",
                },
                "betOffers": [
                    {
                        "id": 2001,
                        "eventId": 1001,
                        "betOfferType": {"name": "Match"},
                        "criterion": {"label": "Moneyline"},
                        "outcomes": [
                            {"label": "New York Mets", "odds": 2450, "status": "OPEN", "type": "OT_ONE"},
                            {"label": "Atlanta Braves", "odds": 1610, "status": "OPEN", "type": "OT_TWO"},
                        ],
                    },
                    {
                        "id": 2003,
                        "eventId": 1001,
                        "betOfferType": {"name": "Handicap"},
                        "criterion": {"label": "Run Line"},
                        "tags": ["MAIN_LINE"],
                        "outcomes": [
                            {"label": "New York Mets", "odds": 1850, "status": "OPEN", "line": 1500, "type": "OT_ONE"},
                            {
                                "label": "Atlanta Braves",
                                "odds": 1950,
                                "status": "OPEN",
                                "line": -1500,
                                "type": "OT_TWO",
                            },
                        ],
                    },
                    {
                        "id": 2004,
                        "eventId": 1001,
                        "betOfferType": {"name": "Over/Under"},
                        "criterion": {"label": "Total Runs"},
                        "tags": ["MAIN_LINE"],
                        "outcomes": [
                            {"label": "Over", "odds": 1910, "status": "OPEN", "line": 8500, "type": "OT_OVER"},
                            {"label": "Under", "odds": 1910, "status": "OPEN", "line": 8500, "type": "OT_UNDER"},
                        ],
                    },
                ],
            },
            {
                "event": {
                    "id": 1002,
                    "name": "San Francisco Giants - Los Angeles Dodgers",
                    "homeName": "Los Angeles Dodgers",
                    "awayName": "San Francisco Giants",
                    "start": "2026-04-03T20:00:00Z",
                    "state": "NOT_STARTED",
                },
                "betOffers": [
                    {
                        "id": 2002,
                        "eventId": 1002,
                        "betOfferType": {"name": "Match"},
                        "criterion": {"label": "Moneyline"},
                        "outcomes": [
                            {"label": "San Francisco Giants", "odds": 2950, "status": "OPEN", "type": "OT_ONE"},
                            {"label": "Los Angeles Dodgers", "odds": 1420, "status": "OPEN", "type": "OT_TWO"},
                        ],
                    },
                ],
            },
        ],
    }


# ---------- BetMGM mock response ----------


@pytest.fixture()
def betmgm_raw_response():
    """Minimal BetMGM CDS API fixtures response (optionMarkets format)."""
    return {
        "fixtures": [
            {
                "id": "mgm1",
                "name": {"value": "New York Mets at Atlanta Braves"},
                "startDate": "2026-04-03T18:00:00Z",
                "participants": [
                    {"name": {"value": "New York Mets"}, "properties": {"type": "AwayTeam"}},
                    {"name": {"value": "Atlanta Braves"}, "properties": {"type": "HomeTeam"}},
                ],
                "optionMarkets": [
                    {
                        "id": 1,
                        "name": {"value": "Moneyline"},
                        "status": "Visible",
                        "options": [
                            {
                                "name": {"value": "Mets"},
                                "status": "Visible",
                                "price": {"americanOdds": 140, "odds": 2.40},
                            },
                            {
                                "name": {"value": "Braves"},
                                "status": "Visible",
                                "price": {"americanOdds": -161, "odds": 1.62},
                            },
                        ],
                    },
                    {
                        "id": 2,
                        "name": {"value": "Run Line Spread"},
                        "status": "Visible",
                        "options": [
                            {
                                "name": {"value": "New York Mets +1.5"},
                                "status": "Visible",
                                "price": {"americanOdds": -125, "odds": 1.80},
                                "attr": "+1.5",
                            },
                            {
                                "name": {"value": "Atlanta Braves -1.5"},
                                "status": "Visible",
                                "price": {"americanOdds": 100, "odds": 2.00},
                                "attr": "-1.5",
                            },
                        ],
                    },
                    {
                        "id": 3,
                        "name": {"value": "Totals"},
                        "status": "Visible",
                        "options": [
                            {
                                "name": {"value": "Over 8.5"},
                                "status": "Visible",
                                "price": {"americanOdds": -115, "odds": 1.87},
                                "totalsPrefix": "Over",
                                "attr": "8.5",
                            },
                            {
                                "name": {"value": "Under 8.5"},
                                "status": "Visible",
                                "price": {"americanOdds": -105, "odds": 1.95},
                                "totalsPrefix": "Under",
                                "attr": "8.5",
                            },
                        ],
                    },
                ],
                "games": [],
            },
            {
                "id": "mgm2",
                "name": {"value": "San Francisco Giants at Los Angeles Dodgers"},
                "startDate": "2026-04-03T20:00:00Z",
                "participants": [
                    {"name": {"value": "San Francisco Giants"}, "properties": {"type": "AwayTeam"}},
                    {"name": {"value": "Los Angeles Dodgers"}, "properties": {"type": "HomeTeam"}},
                ],
                "optionMarkets": [
                    {
                        "id": 4,
                        "name": {"value": "Moneyline"},
                        "status": "Visible",
                        "options": [
                            {
                                "name": {"value": "Giants"},
                                "status": "Visible",
                                "price": {"americanOdds": 195, "odds": 2.95},
                            },
                            {
                                "name": {"value": "Dodgers"},
                                "status": "Visible",
                                "price": {"americanOdds": -238, "odds": 1.42},
                            },
                        ],
                    },
                ],
                "games": [],
            },
        ],
    }


# ---------- Caesars mock response ----------


@pytest.fixture()
def caesars_raw_response():
    """Minimal Caesars americanwagering API response."""
    return {
        "competitions": [
            {
                "id": "comp1",
                "name": "MLB",
                "events": [
                    {
                        "id": "czr1",
                        "name": "New York Mets @ Atlanta Braves",
                        "startTime": "2026-04-03T18:00:00Z",
                        "competitors": [
                            {"name": "New York Mets", "type": "AWAY"},
                            {"name": "Atlanta Braves", "type": "HOME"},
                        ],
                        "markets": [
                            {
                                "name": "Moneyline",
                                "display": True,
                                "active": True,
                                "selections": [
                                    {"name": "New York Mets", "price": {"a": "+135", "d": 2.35}},
                                    {"name": "Atlanta Braves", "price": {"a": "-160", "d": 1.63}},
                                ],
                            },
                            {
                                "name": "Run Line",
                                "display": True,
                                "active": True,
                                "line": 1.5,
                                "selections": [
                                    {
                                        "name": "New York Mets",
                                        "price": {"a": "-130", "d": 1.77, "handicap": 1.5},
                                    },
                                    {
                                        "name": "Atlanta Braves",
                                        "price": {"a": "+110", "d": 2.10, "handicap": -1.5},
                                    },
                                ],
                            },
                            {
                                "name": "Total Runs",
                                "display": True,
                                "active": True,
                                "line": 8.5,
                                "selections": [
                                    {"name": "Over", "price": {"a": "-110", "d": 1.91, "handicap": 8.5}},
                                    {"name": "Under", "price": {"a": "-110", "d": 1.91, "handicap": 8.5}},
                                ],
                            },
                        ],
                    },
                    {
                        "id": "czr2",
                        "name": "San Francisco Giants @ Los Angeles Dodgers",
                        "startTime": "2026-04-03T20:00:00Z",
                        "competitors": [
                            {"name": "San Francisco Giants", "type": "AWAY"},
                            {"name": "Los Angeles Dodgers", "type": "HOME"},
                        ],
                        "markets": [
                            {
                                "name": "Moneyline",
                                "display": True,
                                "active": True,
                                "selections": [
                                    {"name": "San Francisco Giants", "price": {"a": "+200", "d": 3.00}},
                                    {"name": "Los Angeles Dodgers", "price": {"a": "\u2212245", "d": 1.41}},
                                ],
                            },
                        ],
                    },
                ],
            }
        ],
    }
