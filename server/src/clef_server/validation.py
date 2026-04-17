"""ABC score validation utilities."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def run_validation(score_path: Path, plan_path: Path, report_path: Path, session_id: str = "") -> list[dict]:
    """Run validate_abc and return list of FAIL issues (empty if all pass).

    Returns list of {"category": ..., "voice": ..., "message": ...}.
    """
    from clef_server.tools import validate_abc

    result = validate_abc(str(score_path), str(plan_path), str(report_path))
    if "error" in result:
        logger.error("validate_abc error: %s", result["error"])
        return []

    if not report_path.exists():
        return []

    report = json.loads(report_path.read_text(encoding="utf-8"))
    fails = report.get("fails", [])
    # Filter out known artifacts
    real_fails = [f for f in fails if not f.get("known_artifact", False)]
    if real_fails:
        logger.warning(
            "Session %s: %d validation FAIL(s): %s",
            session_id,
            len(real_fails),
            "; ".join(f"{f['voice']}:{f['category']}" for f in real_fails),
        )
    return real_fails


def format_validation_feedback(failures: list[dict]) -> str:
    """Format validation FAIL items into a feedback string for agents."""
    if not failures:
        return ""
    lines = ["VALIDATION FAILURES (must fix before proceeding):"]
    for f in failures:
        lines.append(f"- [{f['category']}] {f['voice']}: {f['message']}")
    lines.append("You MUST fix these issues in your output. Re-check every measure's duration.")
    return "\n".join(lines)


def run_validation_from_abc(
    abc_text: str,
    plan_path: Path,
    report_path: Path,
    workdir: Path,
    voice_label: str = "",
) -> list[dict]:
    """Write ABC to temp file, validate, return failures."""
    from clef_server.tools import validate_abc as validate_tool

    safe_label = voice_label.replace(":", "_").replace("+", "_").replace(" ", "_")
    tmp_abc = Path(workdir) / f"_tmp_{safe_label}.abc"
    tmp_abc.write_text(abc_text, encoding="utf-8")

    try:
        result = validate_tool(str(tmp_abc), str(plan_path), str(report_path))
    except Exception as e:
        logger.warning("Validation failed: %s", e)
        return [{"category": "validation_error", "voice": voice_label, "message": str(e)}]

    if isinstance(result, dict) and "error" in result:
        return [{"category": "validation_error", "voice": voice_label, "message": result["error"]}]

    # Read report
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            fails = [
                {"category": f.get("category", ""), "voice": f.get("voice", voice_label), "message": f.get("message", "")}
                for f in report.get("fails", [])
                if not f.get("known_artifact", False)
            ]
            return fails
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Report parse failed: %s", e)
            return []
    return []
