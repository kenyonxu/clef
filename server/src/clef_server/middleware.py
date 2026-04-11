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

# Token budgets and conversion for skills section
_SKILL_TOKEN_BUDGET = 4000
_CHARS_PER_TOKEN = 4

# Character limits for session context truncation
_PLAN_CHAR_LIMIT = 8000
_SCORE_CHAR_LIMIT = 12000


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

    def build_skills_section(self) -> str:
        """Build reference materials from loaded theory skills.

        Truncates proportionally if total exceeds the token budget.
        Returns an empty string if no skills are loaded.
        """
        if not self._skill_cache:
            return ""

        parts = []
        for skill_name, content in self._skill_cache.items():
            parts.append(f"## {skill_name}\n\n{content}")

        full_text = "\n\n---\n\n".join(parts)

        budget_chars = _SKILL_TOKEN_BUDGET * _CHARS_PER_TOKEN
        if len(full_text) <= budget_chars:
            return full_text

        # Proportional truncation: shrink each skill to fit the budget
        total_len = len(full_text)
        ratio = budget_chars / total_len
        truncated_parts = []
        for skill_name, content in self._skill_cache.items():
            allowed = max(100, int(len(content) * ratio))
            truncated = content[:allowed]
            # Cut at last newline to avoid partial lines
            last_nl = truncated.rfind("\n")
            if last_nl > 0:
                truncated = truncated[:last_nl]
            truncated_parts.append(
                f"## {skill_name}\n\n{truncated}\n\n[...truncated for token budget...]"
            )

        return "\n\n---\n\n".join(truncated_parts)

    def build_session_context(
        self,
        plan: dict | None = None,
        score_abc: str | None = None,
        workdir: str = "",
    ) -> str:
        """Build session context string from plan, score, and workdir.

        Each section is independently truncated if it exceeds its character limit.
        Returns an empty string if no context is provided.
        """
        parts = []

        if plan:
            plan_json = json.dumps(plan, indent=2, ensure_ascii=False)
            if len(plan_json) > _PLAN_CHAR_LIMIT:
                plan_json = plan_json[:_PLAN_CHAR_LIMIT]
                last_nl = plan_json.rfind("\n")
                if last_nl > 0:
                    plan_json = plan_json[:last_nl]
            parts.append(
                "## Current Plan (plan.json)\n\n```json\n" + plan_json + "\n```"
            )

        if score_abc:
            score_text = score_abc
            if len(score_text) > _SCORE_CHAR_LIMIT:
                score_text = score_text[:_SCORE_CHAR_LIMIT]
                last_nl = score_text.rfind("\n")
                if last_nl > 0:
                    score_text = score_text[:last_nl]
            parts.append("## Current Score (score.abc)\n\n```\n" + score_text + "\n```")

        if workdir:
            parts.append(f"Working directory: {workdir}")

        return "\n\n---\n\n".join(parts)

    def build_context(
        self,
        plan: dict | None = None,
        score_abc: str | None = None,
        workdir: str = "",
    ) -> str:
        """Backward-compatible context builder combining skills + session.

        Returns the concatenation of skills section and session context,
        separated by a horizontal rule.
        """
        skills_section = self.build_skills_section()
        session_context = self.build_session_context(
            plan=plan, score_abc=score_abc, workdir=workdir,
        )
        parts = [p for p in (skills_section, session_context) if p]
        return "\n\n---\n\n".join(parts)
