"""PostToolUse hook: log Agent tool calls for cost monitoring.

Reads JSON from stdin (tool_name, tool_input, tool_output),
extracts agent metadata, appends to .clef-work/agent_cost_log.jsonl.
"""

import json
import sys
import re
from datetime import datetime
from pathlib import Path


def infer_step(prompt: str) -> str:
    """Infer workflow step from agent prompt text."""
    p = prompt.lower()
    if any(k in p for k in ("step 0", "需求解析")):
        return "0"
    if any(k in p for k in ("step 1b", "方向小样", "direction sample", "demo")):
        return "1b"
    if any(k in p for k in ("step 1a", "规划", "plan.json")):
        return "1a"
    if any(k in p for k in ("step 2a", "首轮", "full creation", "完整创作")):
        return "2a"
    if any(k in p for k in ("step 2b", "iter", "迭代")):
        m = re.search(r"iter[^\d]*(\d+)", p)
        return f"2b-iter{m.group(1)}" if m else "2b"
    if any(k in p for k in ("step 3", "表现力", "expression", "orchestrat")):
        return "3"
    if any(k in p for k in ("review", "评审")):
        return "review"
    if any(k in p for k in ("revision", "格式修正")):
        return "revision"
    if any(k in p for k in ("leader", "调度")):
        return "leader"
    return "unknown"


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return

        data = json.loads(raw)
        tool_name = data.get("tool_name", "")

        if tool_name != "Agent":
            return

        tool_input = data.get("tool_input", {})
        tool_output = data.get("tool_output", "")
        prompt = tool_input.get("prompt", "")

        agent = tool_input.get("subagent_type", "unknown")
        model = tool_input.get("model", "")
        step = infer_step(prompt)

        log_dir = Path(".clef-work")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "agent_cost_log.jsonl"

        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "agent": agent,
            "model": model,
            "step": step,
            "prompt_chars": len(prompt),
            "output_chars": len(str(tool_output)),
        }

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    except Exception:
        pass


if __name__ == "__main__":
    main()
