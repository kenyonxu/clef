"""AF @tool wrappers for existing Python toolchain scripts.

Each function wraps a public API from .claude/skills/clef-compose/scripts/.
"""

import json
import sys
from pathlib import Path
from typing import Annotated

# Mock agent_framework at import level if not installed (for test environments)
try:
    from agent_framework import tool
except ImportError:
    # Create a no-op @tool decorator for environments without AF installed
    def tool(func=None, **kwargs):
        def decorator(f):
            f._is_tool = True
            f.name = kwargs.get("name", f.__name__)
            return f
        if func:
            return decorator(func)
        return decorator

# Resolve scripts directory relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / ".claude" / "skills" / "clef-compose" / "scripts"

# Ensure scripts are importable
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


@tool
def read_file(path: Annotated[str, "Absolute or relative file path to read"]) -> str:
    """Read file contents as UTF-8 text."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return p.read_text(encoding="utf-8")


@tool
def write_file(
    path: Annotated[str, "Absolute or relative file path to write"],
    content: Annotated[str, "File content to write (UTF-8 text)"],
) -> dict:
    """Write content to file, creating parent directories as needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"path": str(p)}


@tool
def validate_abc(
    abc_file: Annotated[str, "Path to ABC file"],
    plan_file: Annotated[str, "Path to plan.json"],
    output: Annotated[str, "Path for output report JSON"],
) -> dict:
    """Validate ABC file against plan.json (8 checks: key, range, overlap, interval, duration, alignment, sweet_spot, channel)."""
    try:
        from validate_abc import validate
        report = validate(str(abc_file), str(plan_file))
        report.to_json(output)
        return {"report": {"is_valid": report.is_valid}, "has_failures": not report.is_valid}
    except ImportError as e:
        return {"error": f"Missing dependency: {e}", "has_failures": True}
    except Exception as e:
        return {"error": str(e), "has_failures": True}


@tool
def abc_to_midi(
    input_abc: Annotated[str, "Path to input ABC file"],
    output_mid: Annotated[str, "Path for output MIDI file"],
) -> dict:
    """Convert ABC notation file to MIDI."""
    try:
        from abc_to_midi import abc_to_midi as _abc_to_midi
        abc_text = Path(input_abc).read_text(encoding="utf-8")
        midi = _abc_to_midi(abc_text, auto_legato=True)
        midi.save(output_mid)
        return {"output": output_mid}
    except ImportError as e:
        return {"error": f"Missing dependency: {e}", "has_failures": True}
    except Exception as e:
        return {"error": str(e)}


@tool
def abc_lint(
    abc_content: Annotated[str, "ABC notation string to lint"],
    plan_path: Annotated[str, "Optional path to plan.json"] = "",
) -> dict:
    """Lightweight ABC format check (zero dependencies). Checks: natural signs, phantom voices, double barlines, measure duration, register."""
    try:
        from abc_lint import lint
        plan = None
        if plan_path:
            plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        result = lint(abc_content, plan)
        return {
            "key": result.get("key", ""),
            "pass": result.get("pass", True),
            "issues": result.get("issues", []),
            "count": result.get("total_issues", 0),
        }
    except Exception as e:
        return {"error": str(e), "issues": [], "count": 0}


@tool
def merge_abc(
    plan: Annotated[str, "Path to plan.json"],
    fragments: Annotated[dict, "Dict of voice label to ABC content, e.g. {'V:1': '...'}"],
    output: Annotated[str, "Path for merged output ABC file"],
) -> dict:
    """Merge multiple voice ABC fragments into a single score.abc."""
    try:
        from merge_abc import merge
        plan_dict = json.loads(Path(plan).read_text(encoding="utf-8"))
        merged = merge(plan_dict, fragments, mode="full")
        Path(output).write_text(merged, encoding="utf-8")
        return {"output": output}
    except Exception as e:
        return {"error": str(e)}


@tool
def inject_expression(
    midi_file: Annotated[str, "Path to base MIDI file"],
    plan_file: Annotated[str, "Path to expression_plan.json"],
    output: Annotated[str, "Path for output MIDI with expression"],
) -> dict:
    """Inject CC/pitch bend expression data into MIDI file."""
    try:
        from inject_expression import inject as _inject
        _inject(midi_file, plan_file, output)
        return {"output": output}
    except ImportError as e:
        return {"error": f"Missing dependency: {e}", "has_failures": True}
    except Exception as e:
        return {"error": str(e)}


@tool
def snapshot(
    step: Annotated[int, "Step number for logging"],
    output: Annotated[str, "Path for snapshot ABC file"],
    note: Annotated[str, "Description of this step"] = "",
) -> dict:
    """Backup current score.abc and log step progress."""
    try:
        from snapshot import snapshot as _snapshot
        workdir = str(Path(output).parent)
        ret = _snapshot(step=step, output=output, note=note, workdir=workdir)
        return {"snapshot": output, "exit_code": ret}
    except Exception as e:
        return {"error": str(e)}


# === Tool Registry ===

TOOLS_REGISTRY: dict[str, object] = {
    "read_file": read_file,
    "write_file": write_file,
    "validate_abc": validate_abc,
    "abc_to_midi": abc_to_midi,
    "abc_lint": abc_lint,
    "merge_abc": merge_abc,
    "inject_expression": inject_expression,
    "snapshot": snapshot,
}

_AGENT_TOOL_MAP: dict[str, list[str]] = {
    "clef-composer": ["read_file", "write_file", "validate_abc", "abc_lint"],
    "clef-harmonist": ["read_file", "write_file", "validate_abc", "abc_lint"],
    "clef-rhythmist": ["read_file", "write_file", "validate_abc", "abc_lint"],
    "clef-reviewer": ["read_file", "validate_abc", "abc_lint"],
    "clef-revision": ["read_file", "write_file"],
    "clef-orchestrator": ["read_file", "write_file", "abc_to_midi", "inject_expression"],
}


def get_tools_for_agent(agent_name: str) -> list:
    """Return the list of @tool functions assigned to a given agent."""
    tool_names = _AGENT_TOOL_MAP.get(agent_name, [])
    return [TOOLS_REGISTRY[n] for n in tool_names if n in TOOLS_REGISTRY]
