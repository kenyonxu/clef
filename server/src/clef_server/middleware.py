"""ClefContextMiddleware — injects theory skills + session context into Agent calls."""

import json
from pathlib import Path


# Skill name → SKILL.md file name mapping
_SKILL_FILE_MAP = {
    "abc": "theory-abc",
    "melody": "theory-melody",
    "harmony": "theory-harmony",
    "rhythm": "theory-rhythm",
    "structure": "theory-structure",
    "orchestration": "theory-orchestration",
}


class ClefContextMiddleware:
    """Prepends theory skill content and session context to agent instructions."""

    def __init__(self, skills: list[str], skills_dir: Path):
        self._skill_cache: dict[str, str] = {}
        self._skills_dir = skills_dir
        self._load_skills(skills)

    def _load_skills(self, skill_names: list[str]) -> None:
        for name in skill_names:
            dir_name = _SKILL_FILE_MAP.get(name)
            if not dir_name:
                continue
            skill_md = self._skills_dir / dir_name / "SKILL.md"
            if skill_md.exists():
                self._skill_cache[dir_name] = skill_md.read_text(encoding="utf-8")

    def build_context(
        self,
        plan: dict | None = None,
        score_abc: str | None = None,
        workdir: str = "",
    ) -> str:
        parts = []
        for skill_name, content in self._skill_cache.items():
            parts.append(f"## {skill_name}\n\n{content}")
        if plan:
            parts.append("## Current Plan (plan.json)\n\n```json\n" + json.dumps(plan, indent=2, ensure_ascii=False) + "\n```")
        if score_abc:
            parts.append("## Current Score (score.abc)\n\n```\n" + score_abc + "\n```")
        if workdir:
            parts.append(f"Working directory: {workdir}")
        return "\n\n---\n\n".join(parts)
