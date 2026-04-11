"""Prompt parity tests — verify music constraints are consistent
between clef-compose (.claude/agents/) and clef-server (server/config/prompts/).
"""

import re
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_YAML = PROJECT_ROOT / "server" / "config" / "prompts" / "shared_constraints.yaml"
COMPOSE_AGENTS = PROJECT_ROOT / ".claude" / "agents"
SERVER_PROMPTS = PROJECT_ROOT / "server" / "config" / "prompts"

# Agents that exist in both locations
SHARED_AGENTS = ["clef-composer", "clef-harmonist", "clef-rhythmist",
                 "clef-reviewer", "clef-orchestrator", "clef-revision"]


@pytest.fixture
def shared_constraints():
    """Load shared_constraints.yaml."""
    with open(SHARED_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_agent(name: str, location: str) -> str:
    """Read agent prompt from compose or server location."""
    if location == "compose":
        path = COMPOSE_AGENTS / f"{name}.md"
    else:
        path = SERVER_PROMPTS / f"{name}.md"
    if not path.exists():
        pytest.skip(f"{path} not found")
    return path.read_text(encoding="utf-8")


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from clef-compose prompts."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2]
    return text


class TestSharedConstraintsExist:
    """Verify shared_constraints.yaml has all required sections."""

    def test_yaml_loads(self, shared_constraints):
        assert isinstance(shared_constraints, dict)

    def test_has_global_constraints(self, shared_constraints):
        assert "global_constraints" in shared_constraints
        assert len(shared_constraints["global_constraints"]) >= 4

    def test_has_duration_table(self, shared_constraints):
        assert "duration_table" in shared_constraints
        entries = shared_constraints["duration_table"]["entries"]
        assert len(entries) >= 5

    def test_has_abc_octave_rules(self, shared_constraints):
        assert "abc_octave_rules" in shared_constraints
        assert len(shared_constraints["abc_octave_rules"]) >= 3

    def test_has_self_check_items(self, shared_constraints):
        assert "self_check_items" in shared_constraints
        assert len(shared_constraints["self_check_items"]) >= 4

    def test_has_sf2_parameters(self, shared_constraints):
        assert "sf2_parameters" in shared_constraints
        assert len(shared_constraints["sf2_parameters"]) >= 5

    def test_has_drum_map(self, shared_constraints):
        assert "drum_map" in shared_constraints
        assert len(shared_constraints["drum_map"]["entries"]) >= 9


class TestGlobalConstraintsParity:
    """Verify global constraints appear in both prompt sets."""

    @pytest.mark.parametrize("agent_name", SHARED_AGENTS)
    def test_global_constraint_in_both(self, agent_name, shared_constraints):
        """Each global constraint should appear in both compose and server prompts."""
        compose_text = _strip_frontmatter(_read_agent(agent_name, "compose"))
        server_text = _read_agent(agent_name, "server")

        for gc in shared_constraints["global_constraints"]:
            # Skip constraints that only apply to certain agents
            if gc["id"] == "G3" and agent_name in ("clef-reviewer",):
                continue  # reviewer doesn't output ABC

            keyword = gc["text"][:20]  # First 20 chars as search key
            if keyword in compose_text:
                assert keyword in server_text, (
                    f"Global constraint '{gc['text'][:40]}...' found in compose "
                    f"but missing from server prompt for {agent_name}"
                )


class TestDurationTableParity:
    """Verify duration table entries appear in agent prompts with self-checks."""

    @pytest.mark.parametrize("agent_name", ["clef-composer", "clef-harmonist", "clef-rhythmist"])
    def test_duration_entries_present(self, agent_name, shared_constraints):
        """Key duration entries should be in both prompts."""
        compose_text = _strip_frontmatter(_read_agent(agent_name, "compose"))
        server_text = _read_agent(agent_name, "server")

        # Check a few key entries
        key_entries = ["f2", "f4", "f/2", "z2"]
        for notation in key_entries:
            if notation in compose_text:
                assert notation in server_text, (
                    f"Duration notation '{notation}' in compose but not server for {agent_name}"
                )


class TestABCOctaveRulesParity:
    """Verify ABC octave rules appear in both prompt sets."""

    @pytest.mark.parametrize("agent_name", ["clef-composer", "clef-harmonist", "clef-rhythmist"])
    def test_octave_rules_present(self, agent_name, shared_constraints):
        """ABC octave rules should appear in both prompts."""
        compose_text = _strip_frontmatter(_read_agent(agent_name, "compose"))
        server_text = _read_agent(agent_name, "server")

        # Check key phrases from octave rules
        key_phrases = ["C4 起始八度", "C3 起始八度", "降低八度", "升高八度"]
        for phrase in key_phrases:
            if phrase in compose_text:
                assert phrase in server_text, (
                    f"Octave rule '{phrase}' in compose but not server for {agent_name}"
                )


class TestDrumMapParity:
    """Verify drum map is consistent between compose and server rhythmist."""

    def test_drum_map_in_rhythmist(self, shared_constraints):
        compose_text = _strip_frontmatter(_read_agent("clef-rhythmist", "compose"))
        server_text = _read_agent("clef-rhythmist", "server")

        for entry in shared_constraints["drum_map"]["entries"]:
            notation = entry["notation"]
            assert notation in compose_text, f"Drum {notation} missing from compose rhythmist"
            assert notation in server_text, f"Drum {notation} missing from server rhythmist"


class TestSF2ParametersParity:
    """Verify SF2 parameter descriptions are consistent."""

    @pytest.mark.parametrize("agent_name", ["clef-composer", "clef-harmonist", "clef-rhythmist"])
    def test_sf2_params_in_both(self, agent_name, shared_constraints):
        compose_text = _strip_frontmatter(_read_agent(agent_name, "compose"))
        server_text = _read_agent(agent_name, "server")

        for param in shared_constraints["sf2_parameters"]:
            name = param["name"]
            if name in compose_text:
                assert name in server_text, (
                    f"SF2 param '{name}' in compose but not server for {agent_name}"
                )


class TestSelfCheckParity:
    """Verify self-check items appear in both prompt sets."""

    @pytest.mark.parametrize("agent_name", ["clef-composer", "clef-harmonist", "clef-rhythmist"])
    def test_self_check_items(self, agent_name, shared_constraints):
        compose_text = _strip_frontmatter(_read_agent(agent_name, "compose"))
        server_text = _read_agent(agent_name, "server")

        for item in shared_constraints["self_check_items"]:
            name = item["name"]
            if name in compose_text:
                assert name in server_text, (
                    f"Self-check '{name}' in compose but not server for {agent_name}"
                )
