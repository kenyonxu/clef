"""AF @tool wrappers for existing Python toolchain scripts.

Each function wraps a public API from .claude/skills/clef-compose/scripts/.
"""

import json
import re
import sys
from dataclasses import dataclass
from enum import Enum
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


# === Tool Safety Metadata ===

class ToolSafety(Enum):
    READ_ONLY = "read_only"
    IDEMPOTENT_WRITE = "idempotent"
    EXCLUSIVE_WRITE = "exclusive"


@dataclass(frozen=True)
class ToolMeta:
    safety: ToolSafety
    estimated_tokens: int = 500


_TOOL_META: dict[str, ToolMeta] = {
    "read_file": ToolMeta(ToolSafety.READ_ONLY, 1000),
    "write_file": ToolMeta(ToolSafety.EXCLUSIVE_WRITE, 200),
    "validate_abc": ToolMeta(ToolSafety.READ_ONLY, 800),
    "abc_lint": ToolMeta(ToolSafety.READ_ONLY, 400),
    "abc_to_midi": ToolMeta(ToolSafety.READ_ONLY, 100),
    "merge_abc": ToolMeta(ToolSafety.EXCLUSIVE_WRITE, 200),
    "inject_expression": ToolMeta(ToolSafety.EXCLUSIVE_WRITE, 100),
    "snapshot": ToolMeta(ToolSafety.IDEMPOTENT_WRITE, 50),
    "fix_measure_duration": ToolMeta(ToolSafety.READ_ONLY, 200),
}


# === fix_measure_duration helpers ===

_NOTE_RE = re.compile(
    r"([\\^_=]*"           # accidental
    r"[a-gA-G]"            # note name
    r"[',]*"               # octave marks
    r")"
    r"(\d*(?:/\d+)?)"      # duration: "2", "3", "/2", "3/2", or "" (=1)
)
_REST_RE = re.compile(r"(z)(\d*(?:/\d+)?)")
_CHORD_RE = re.compile(r"(\[[^\]]+\])(\d*(?:/\d+)?)")
_TUPLET_RE = re.compile(r"\((\d+)")


def _parse_abc_duration(duration_str: str) -> float:
    """Convert ABC duration string to float units.

    "" -> 1.0, "2" -> 2.0, "/2" -> 0.5, "3/2" -> 1.5
    """
    if not duration_str:
        return 1.0
    if "/" in duration_str:
        parts = duration_str.split("/")
        num = int(parts[0]) if parts[0] else 1
        den = int(parts[1])
        return num / den
    return float(duration_str)


def _duration_to_str(units: float) -> str:
    """Convert float units back to ABC duration string."""
    if units == 1.0:
        return ""
    if units == int(units):
        return str(int(units))
    # Try common fractions
    for den in (2, 3, 4, 8):
        if abs(units * den - round(units * den)) < 0.01:
            num = int(round(units * den))
            if num == 1:
                return f"/{den}"
            return f"{num}/{den}"
    return str(units)


def _count_measure_units_clean(measure_text: str) -> float:
    """Count total duration units in a measure, handling chords and tuplets.

    Clean implementation:
    1. Extract chords as single events
    2. Parse tuplets and apply ratio
    3. Count remaining notes/rests normally
    """
    text = measure_text.strip()

    # Collect all note/rest/chord events with their positions
    events: list[tuple[int, int, float]] = []  # (start, end, duration)

    # Chords first (they contain note characters)
    for m in _CHORD_RE.finditer(text):
        dur = _parse_abc_duration(m.group(2))
        events.append((m.start(), m.end(), dur))

    # Rests
    for m in _REST_RE.finditer(text):
        dur = _parse_abc_duration(m.group(2))
        events.append((m.start(), m.end(), dur))

    # Notes (skip those already inside chords)
    chord_ranges = [(e[0], e[1]) for e in events]
    for m in _NOTE_RE.finditer(text):
        # Check if this note is inside a chord
        inside_chord = False
        for cs, ce in chord_ranges:
            if cs <= m.start() < ce:
                inside_chord = True
                break
        if not inside_chord:
            dur = _parse_abc_duration(m.group(2))
            events.append((m.start(), m.end(), dur))

    # Sort by position
    events.sort(key=lambda e: e[0])

    # Find tuplet markers and apply ratio to following N events
    for m in _TUPLET_RE.finditer(text):
        ratio = int(m.group(1))
        notes_in_group = ratio
        tuplet_end_pos = m.end()

        # Find events that come after this tuplet marker
        affected_indices: list[int] = []
        for i, (start, end, dur) in enumerate(events):
            if start >= tuplet_end_pos and len(affected_indices) < notes_in_group:
                affected_indices.append(i)

        if affected_indices:
            tuplet_factor = (ratio - 1) / ratio if ratio > 1 else 1.0
            for i in affected_indices:
                s, e, d = events[i]
                events[i] = (s, e, d * tuplet_factor)

    return sum(e[2] for e in events)


def _fix_single_measure(
    measure_text: str,
    target: float,
    max_deviation: float = 2.0,
) -> tuple[str, dict | None]:
    """Try to fix a single measure's duration by adjusting the last note/rest.

    Returns (fixed_text, fix_info). fix_info is None if no fix needed.
    """
    actual = _count_measure_units_clean(measure_text)
    diff = actual - target

    if abs(diff) < 0.01:
        return measure_text, None

    if abs(diff) > max_deviation + 0.01:
        # Too far off to fix mechanically
        return measure_text, {"skipped": True, "actual_units": actual, "target_units": target}

    # Find the last note, rest, or chord to adjust
    # We need to find the last event and modify its duration
    text = measure_text

    # Find all events with positions
    all_events: list[tuple[int, int, str, str]] = []  # (start, end, prefix, duration_str)

    # Chords
    for m in _CHORD_RE.finditer(text):
        all_events.append((m.start(), m.end(), m.group(1), m.group(2)))
    # Rests
    for m in _REST_RE.finditer(text):
        all_events.append((m.start(), m.end(), m.group(1), m.group(2)))
    # Notes
    chord_ranges = [(e[0], e[1]) for e in all_events]
    for m in _NOTE_RE.finditer(text):
        inside_chord = any(cs <= m.start() < ce for cs, ce in chord_ranges)
        if not inside_chord:
            all_events.append((m.start(), m.end(), m.group(1), m.group(2)))

    if not all_events:
        return measure_text, {"skipped": True, "actual_units": actual, "target_units": target}

    # Sort by position, take the last one
    all_events.sort(key=lambda e: e[0])
    last_start, last_end, last_prefix, last_dur_str = all_events[-1]
    last_dur = _parse_abc_duration(last_dur_str)
    new_dur = last_dur - diff  # diff = actual - target, so subtract to reach target

    if new_dur < 0.01:
        # Duration would be 0 or negative: remove the event
        # Remove trailing whitespace before the event too
        before = text[:last_start].rstrip()
        fixed = before + text[last_end:]
        return fixed, {
            "action": "remove",
            "target": "note" if not last_prefix.startswith("z") and not last_prefix.startswith("[") else ("rest" if last_prefix == "z" else "chord"),
            "from": text[last_start:last_end],
            "to": "(removed)",
            "actual_units": actual,
            "target_units": target,
        }

    new_dur_str = _duration_to_str(new_dur)
    old_event = text[last_start:last_end]
    new_event = last_prefix + new_dur_str

    fixed = text[:last_start] + new_event + text[last_end:]

    action = "shorten" if diff > 0 else "extend"
    target_type = "note"
    if last_prefix == "z":
        target_type = "rest"
    elif last_prefix.startswith("["):
        target_type = "chord"

    return fixed, {
        "action": action,
        "target": target_type,
        "from": old_event,
        "to": new_event,
        "actual_units": actual,
        "target_units": target,
    }


def _validate_path(path: str, workdir: str) -> Path:
    """Resolve path and validate it stays within workdir boundary.

    Raises ValueError if path escapes workdir (path traversal).
    """
    resolved = Path(path).resolve()
    workdir_resolved = Path(workdir).resolve()
    try:
        resolved.relative_to(workdir_resolved)
    except ValueError:
        raise ValueError(
            f"Path '{path}' is outside workdir '{workdir}' (path traversal blocked)"
        )
    return resolved


@tool
def read_file(
    path: Annotated[str, "Absolute or relative file path to read"],
    workdir: Annotated[str, "Working directory for path validation"],
) -> str:
    """Read file contents as UTF-8 text."""
    p = _validate_path(path, workdir)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return p.read_text(encoding="utf-8")


@tool
def write_file(
    path: Annotated[str, "Absolute or relative file path to write"],
    content: Annotated[str, "File content to write (UTF-8 text)"],
    workdir: Annotated[str, "Working directory for path validation"],
) -> dict:
    """Write content to file, creating parent directories as needed."""
    p = _validate_path(path, workdir)
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


@tool
def fix_measure_duration(
    abc_content: Annotated[str, "ABC notation content to fix"],
    target_per_measure: Annotated[float | None, "Target units per measure (None = auto-detect from M:/L:)"] = None,
) -> dict:
    """Mechanically fix measure duration errors in ABC notation content.

    Parses each measure, counts duration units, and fixes measures off by 1-2 units.
    Measures off by >2 units are skipped (left for repair agent).
    """
    try:
        lines = abc_content.split("\n")

        # Parse headers
        m_match = None
        l_base = 4  # ABC standard default L: is 1/4
        header_end = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("M:"):
                m_match = re.match(r"M:(\d+)/(\d+)", stripped)
            elif stripped.startswith("L:"):
                l_match = re.match(r"L:1/(\d+)", stripped)
                if l_match:
                    l_base = int(l_match.group(1))
            elif stripped.startswith("K:"):
                header_end = i + 1
                break

        # Auto-detect target
        if target_per_measure is None:
            if m_match:
                num = int(m_match.group(1))
                den = int(m_match.group(2))
                target_per_measure = num * l_base / den
            else:
                target_per_measure = 4.0  # default 4/4

        # Find music lines (after headers, containing |)
        fixes: list[dict] = []
        passed = True
        measures_checked = 0

        result_lines: list[str] = []
        for i, line in enumerate(lines):
            if "|" not in line or i < header_end:
                result_lines.append(line)
                continue

            # Skip %%MIDI and other directive lines that happen to contain |
            if stripped.startswith("%%"):
                result_lines.append(line)
                continue

            # Split into measures by |
            parts = line.split("|")
            fixed_parts: list[str] = []

            for j, part in enumerate(parts):
                # Skip empty parts (from || or leading/trailing |)
                stripped_part = part.strip()
                if not stripped_part:
                    fixed_parts.append(part)
                    continue

                # Skip voice labels or other non-music content
                if stripped_part.startswith("V:") or stripped_part.startswith("%"):
                    fixed_parts.append(part)
                    continue

                measures_checked += 1
                fixed_text, fix_info = _fix_single_measure(stripped_part, target_per_measure)

                if fix_info is not None:
                    if fix_info.get("skipped"):
                        passed = False
                        fixes.append({
                            "measure": measures_checked,
                            **fix_info,
                        })
                        fixed_parts.append(part)
                    else:
                        passed = False
                        fixes.append({
                            "measure": measures_checked,
                            **fix_info,
                        })
                        # Preserve leading whitespace from original
                        leading = part[:len(part) - len(part.lstrip())]
                        trailing = part[len(part.rstrip()):]
                        fixed_parts.append(leading + fixed_text + trailing)
                else:
                    fixed_parts.append(part)

            result_lines.append("|".join(fixed_parts))

        return {
            "abc": "\n".join(result_lines),
            "fixes": fixes,
            "passed": passed,
            "measures_checked": measures_checked,
        }
    except Exception as e:
        return {"error": str(e), "fixes": [], "passed": False, "measures_checked": 0}


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
    "fix_measure_duration": fix_measure_duration,
}

_AGENT_TOOL_MAP: dict[str, list[str]] = {
    "clef-composer": ["read_file", "write_file", "validate_abc", "abc_lint"],
    "clef-harmonist": ["read_file", "write_file", "validate_abc", "abc_lint"],
    "clef-rhythmist": ["read_file", "write_file", "validate_abc", "abc_lint"],
    "clef-reviewer": ["read_file", "validate_abc", "abc_lint"],
    "clef-revision": ["read_file", "write_file"],
    "clef-orchestrator": ["read_file", "write_file", "abc_to_midi", "inject_expression"],
    "clef-repair": ["read_file", "write_file", "abc_lint", "fix_measure_duration"],
}


def get_tools_for_agent(agent_name: str) -> list:
    """Return the list of @tool functions assigned to a given agent."""
    tool_names = _AGENT_TOOL_MAP.get(agent_name, [])
    return [TOOLS_REGISTRY[n] for n in tool_names if n in TOOLS_REGISTRY]


_PYTHON_TO_JSON_TYPE = {
    str: "string", int: "integer", float: "number",
    bool: "boolean", dict: "object", list: "array",
}


def get_tool_schemas(agent_name: str) -> list[dict]:
    """Generate OpenAI-format tool schemas for an agent's tools."""
    import inspect

    tool_names = _AGENT_TOOL_MAP.get(agent_name, [])
    schemas = []

    for name in tool_names:
        func = TOOLS_REGISTRY.get(name)
        if func is None:
            continue

        # Unwrap FunctionTool to get the underlying Python function
        raw_func = getattr(func, "func", func)

        sig = inspect.signature(raw_func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            annotation = param.annotation
            if annotation is inspect.Parameter.empty:
                param_type = "string"
            elif hasattr(annotation, "__origin__"):
                args = getattr(annotation, "__args__", ())
                raw_type = args[0] if args else str
                param_type = _PYTHON_TO_JSON_TYPE.get(raw_type, "string")
            else:
                param_type = _PYTHON_TO_JSON_TYPE.get(annotation, "string")

            description = ""
            if hasattr(annotation, "__metadata__"):
                for meta in annotation.__metadata__:
                    if isinstance(meta, str):
                        description = meta
                        break
            elif hasattr(annotation, "__args__") and len(getattr(annotation, "__args__", ())) > 1:
                for arg in annotation.__args__[1:]:
                    if isinstance(arg, str):
                        description = arg
                        break

            properties[param_name] = {"type": param_type}
            if description:
                properties[param_name]["description"] = description

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        doc = inspect.getdoc(raw_func) or f"Execute the {name} tool."

        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": doc.split("\n")[0],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
        schemas.append(schema)

    return schemas
