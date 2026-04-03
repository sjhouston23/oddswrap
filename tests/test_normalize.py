"""Tests for oddswrap.normalize."""

from oddswrap.normalize import normalize_team


class TestNormalizeTeam:
    def test_known_alias(self):
        assert normalize_team("NY Mets") == "new york mets"

    def test_already_canonical(self):
        assert normalize_team("new york mets") == "new york mets"

    def test_case_insensitive(self):
        assert normalize_team("NY METS") == "new york mets"

    def test_whitespace_stripped(self):
        assert normalize_team("  NY Mets  ") == "new york mets"

    def test_unknown_passes_through(self):
        assert normalize_team("Some Unknown Team") == "some unknown team"

    def test_nfl_alias(self):
        assert normalize_team("GB Packers") == "green bay packers"

    def test_nhl_alias(self):
        assert normalize_team("NJ Devils") == "new jersey devils"

    def test_nba_alias(self):
        assert normalize_team("GS Warriors") == "golden state warriors"

    def test_st_louis_variants(self):
        assert normalize_team("STL Cardinals") == "st. louis cardinals"
        assert normalize_team("St Louis Cardinals") == "st. louis cardinals"
