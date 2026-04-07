"""Shared test fixtures."""

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

# 项目根目录（clef-dev/）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SERVER_ROOT = PROJECT_ROOT / "server"
SCRIPTS_DIR = PROJECT_ROOT / ".claude" / "skills" / "clef-compose" / "scripts"
AGENTS_DIR = PROJECT_ROOT / ".claude" / "agents"
SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def scripts_dir() -> Path:
    return SCRIPTS_DIR


@pytest.fixture
def agents_dir() -> Path:
    return AGENTS_DIR


@pytest.fixture
def skills_dir() -> Path:
    return SKILLS_DIR


@pytest.fixture
def tmp_workdir(tmp_path: Path) -> Path:
    """Create a temporary .clef-work directory with plan.json."""
    workdir = tmp_path / ".clef-work"
    workdir.mkdir()
    (workdir / "output").mkdir()
    return workdir


@pytest.fixture
def sample_plan() -> dict[str, Any]:
    """Minimal valid plan.json for testing."""
    return {
        "title": "Test Composition",
        "key": "C",
        "time_signature": "4/4",
        "tempo": 120,
        "total_bars": 16,
        "structure": {"sections": [{"name": "A", "bars": 16}]},
        "voices": {
            "1": {"role": "melody", "instrument": "Acoustic Grand Piano", "range": {"min": 60, "max": 84}, "register": {"min": 60, "max": 79}},
            "2": {"role": "harmony", "instrument": "Acoustic Grand Piano", "range": {"min": 48, "max": 72}, "register": {"min": 55, "max": 72}},
            "3": {"role": "bass", "instrument": "Acoustic Bass", "range": {"min": 28, "max": 55}, "register": {"min": 36, "max": 48}},
            "4": {"role": "drums", "instrument": "Standard Kit", "range": {"min": 35, "max": 81}, "register": {"min": 35, "max": 81}},
        },
        "generation_order": ["harmony", "melody", "rhythm"],
    }


@pytest.fixture
def sample_abc() -> str:
    """Minimal valid ABC for testing."""
    return """X:1
T:Test
M:4/4
L:1/4
Q:1/4=120
K:C
%%MIDI channel 1
V:1
"C" C E G c |"G" B d' G |
V:2
%%MIDI channel 2
C, E, G, C |G,, D, G, B, |
V:3
%%MIDI channel 3
C,, |G,,, |
V:4
%%MIDI channel 9
z2 z2 |z2 z2 |"""


@pytest.fixture
def mock_chat_response() -> AsyncMock:
    """Mock AF ChatResponse for unit tests."""
    response = AsyncMock()
    response.text = "OK"
    response.finish_reason = "stop"
    response.usage = AsyncMock()
    response.usage.prompt_tokens = 10
    response.usage.completion_tokens = 5
    return response
