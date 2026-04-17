"""Parse LLM agent responses into structured data."""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def looks_like_abc(text: str) -> bool:
    """Heuristic: does the text look like valid ABC notation?"""
    stripped = text.strip()
    if not stripped:
        return False
    # Must start with a standard ABC header or voice label
    has_abc_header = any(stripped.startswith(h) for h in ("X:", "T:", "M:", "K:", "L:", "V:"))
    # Must contain at least one bar line (|) or note letters
    has_music = "|" in stripped or any(c in stripped for c in "abcdefgABCDEFG")
    return has_abc_header and has_music


def extract_abc(text: str) -> str:
    """Extract ABC notation from agent response text.

    Handles markdown code fences (```abc ... ```) or raw ABC content.
    Rejects text that clearly isn't ABC (tool-call syntax, prose, etc.).
    """
    from clef_server.score_processor import trim_trailing_rests

    text = text.strip()
    # Guard against raw Content objects leaking into text
    if "Content(type=" in text:
        logger.warning("extract_abc: received raw Content object, returning empty")
        return ""
    # Reject text containing tool-call artifacts (DSML, XML tool tags, etc.)
    tool_markers = ("<|DSML|>", "<function_calls>", "</invoke>", "tool_call", "FunctionCall")
    if any(m in text for m in tool_markers):
        logger.warning("extract_abc: response contains tool-call syntax, attempting strip")
        text = strip_tool_markers(text)
        if not looks_like_abc(text):
            logger.warning("extract_abc: stripped text still not ABC, returning empty")
            return ""
    # Try fenced block first
    fence_match = re.search(r"```(?:abc)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    # Raw text must look like ABC
    elif not looks_like_abc(text):
        logger.warning("extract_abc: text does not look like ABC (first 80 chars: %s...), returning empty",
                       text[:80])
        return ""

    # Trim trailing rest-only bars
    text = trim_trailing_rests(text)
    return text


def is_placeholder(text: str) -> bool:
    """Check if extracted ABC is a placeholder (not real music)."""
    lower = text.lower().strip()
    return (
        "placeholder" in lower
        or len(lower) < 10
        or not any(c in lower for c in "|abcdefg'")
    )


def strip_tool_markers(text: str) -> str:
    """Remove known tool-call marker patterns from text.

    Strips DSML blocks, function_calls tags, and other tool-call artifacts.
    Preserves surrounding content.
    """
    # Remove complete DSML blocks: <|DSML|>...content...<|DSML|>
    text = re.sub(r'<\|DSML\|>.*?<\|DSML\|>', '', text, flags=re.DOTALL)
    # Remove individual DSML markers
    text = text.replace('<|DSML|>', '')
    # Remove function_calls blocks
    text = re.sub(r'<function_calls>.*?</function_calls>', '', text, flags=re.DOTALL)
    # Remove individual tags and their content on the same line
    for tag in ('<function_calls>', '</function_calls>', '</invoke>'):
        text = re.sub(rf'^\s*{re.escape(tag)}.*$', '', text, flags=re.MULTILINE)
    # Remove <invoke ...> lines
    text = re.sub(rf'^\s*<invoke\b.*$', '', text, flags=re.MULTILINE)
    # Remove lines that are just tool markers
    for marker in ('tool_call', 'FunctionCall'):
        text = re.sub(rf'^\s*{re.escape(marker)}.*$', '', text, flags=re.MULTILINE)
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def quick_lint_check(abc_text: str, plan_path: Path) -> str | bool:
    """Run abc_lint on extracted ABC. Returns True if clean, or error string for feedback."""
    from clef_server.tools import abc_lint
    result = abc_lint(abc_text, str(plan_path))
    if "error" in result:
        return True  # Lint itself failed -- don't block, accept as-is
    if result.get("pass", True):
        return True
    issues = result.get("issues", [])
    if not issues:
        return True
    lines = [f"ABC 格式检查发现 {len(issues)} 个问题："]
    for issue in issues[:5]:
        lines.append(f"- {issue}")
    if len(issues) > 5:
        lines.append(f"- ...还有 {len(issues) - 5} 个问题")
    return "\n".join(lines)


def extract_json(text: str) -> dict:
    """Extract JSON from agent response, handling markdown fencing."""
    text = text.strip()
    # Reject text containing tool-call artifacts
    tool_markers = ("<|DSML|>", "<function_calls>", "</invoke>", "tool_call", "FunctionCall")
    if any(m in text for m in tool_markers):
        logger.warning("extract_json: response contains tool-call syntax, attempting strip")
        text = strip_tool_markers(text)
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("extract_json: failed to parse JSON, returning revise verdict")
        return {"verdict": "revise"}


def extract_rhythm(response: str) -> str:
    """Extract rhythm skeleton from agent response."""
    import re as _re
    # Reject tool-call artifacts
    tool_markers = ("<|DSML|>", "<function_calls>", "</invoke>", "tool_call", "FunctionCall")
    if any(m in response for m in tool_markers):
        logger.warning("extract_rhythm: response contains tool-call syntax, attempting strip")
        response = strip_tool_markers(response)
    match = _re.search(r"```(?:rhythm)?\s*\n?(.*?)```", response, _re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: look for | separated numbers
    lines = response.strip().split("\n")
    for line in lines:
        if "|" in line and any(c.isdigit() for c in line):
            return line.strip()
    # Nothing recognizable found
    logger.warning("extract_rhythm: no rhythm pattern found in response")
    return ""


def normalize_review(raw: dict) -> dict:
    """Normalize reviewer output into a flat structure for the frontend.

    The reviewer agent outputs nested "dimensions": {"melody": {"score": 7, ...}, ...}.
    The frontend expects flat "scores": {"melody": 7, ...} + "verdict" + "summary".
    """
    result: dict = {"verdict": raw.get("verdict", "pass"), "scores": {}}

    # Extract from nested "dimensions" format (reviewer's standard output)
    dimensions = raw.get("dimensions", {})
    if isinstance(dimensions, dict):
        for key, val in dimensions.items():
            if isinstance(val, dict):
                result["scores"][key] = val.get("score", 0)
            elif isinstance(val, (int, float)):
                result["scores"][key] = val

    # Fallback: if agent returned flat "scores" directly
    if not result["scores"] and "scores" in raw:
        result["scores"] = raw["scores"]

    # Collect all issues into a flat list
    all_issues: list[str] = []
    if isinstance(dimensions, dict):
        for val in dimensions.values():
            if isinstance(val, dict) and "issues" in val:
                for issue in val["issues"]:
                    if isinstance(issue, dict):
                        all_issues.append(issue.get("description", str(issue)))
                    else:
                        all_issues.append(str(issue))
    if not all_issues and "issues" in raw:
        all_issues = raw["issues"]
    result["issues"] = all_issues

    # Summary: prefer explicit field, otherwise derive from overall_score
    if "summary" in raw:
        result["summary"] = raw["summary"]
    elif "overall_score" in raw:
        result["summary"] = f"Overall: {raw['overall_score']}/10"
    else:
        avg = sum(result["scores"].values()) / max(len(result["scores"]), 1)
        result["summary"] = f"Overall: {avg:.1f}/10"

    raw_overall = raw.get("overall_score")
    if raw_overall is not None:
        result["overall_score"] = raw_overall
    else:
        result["overall_score"] = (
            sum(result["scores"].values()) / max(len(result["scores"]), 1)
        )
    return result
