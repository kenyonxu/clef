"""Tests for clef_tools unified CLI entry point."""
import subprocess
import sys
import os

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')
CLEF_TOOLS = os.path.join(SCRIPTS_DIR, 'clef_tools.py')


def test_cli_help():
    result = subprocess.run(
        [sys.executable, CLEF_TOOLS, '--help'],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert 'abc-to-midi' in result.stdout
    assert 'validate' in result.stdout
    assert 'merge' in result.stdout
    assert 'inject' in result.stdout
    assert 'extract-solo' in result.stdout


def test_cli_subcommand_help():
    """Each subcommand should also have its own help."""
    for cmd in ['check-deps', 'abc-to-midi', 'validate', 'merge', 'inject', 'extract-solo']:
        result = subprocess.run(
            [sys.executable, CLEF_TOOLS, cmd, '--help'],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"'{cmd} --help' failed: {result.stderr}"


def test_cli_no_command_fails():
    """Running without a subcommand should fail."""
    result = subprocess.run(
        [sys.executable, CLEF_TOOLS],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0


def test_cli_invalid_command_fails():
    """Running with an unknown subcommand should fail."""
    result = subprocess.run(
        [sys.executable, CLEF_TOOLS, 'nonexistent'],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0


def test_cli_check_deps():
    """check-deps should succeed when music21 and mido are installed."""
    result = subprocess.run(
        [sys.executable, CLEF_TOOLS, 'check-deps'],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"check-deps failed: {result.stderr}"
