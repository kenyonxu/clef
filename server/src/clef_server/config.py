"""Configuration loading — YAML files + environment variable expansion."""

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _expand_env_vars(value: str) -> str:
    """Expand ${VAR} and ${VAR:-default} patterns in string."""
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        if ":-" in var_name:
            var_name, default = var_name.split(":-", 1)
            return os.environ.get(var_name, default)
        env_val = os.environ.get(var_name)
        if env_val is None:
            logger.warning(f"Environment variable {var_name} is not set, using empty string")
            return ""
        return env_val

    return re.sub(r"\$\{([^}]+)\}", _replace, value)


def _expand_dict(d: dict) -> dict:
    """Recursively expand env vars in all string values of a dict."""
    result = {}
    for k, v in d.items():
        if isinstance(v, str):
            result[k] = _expand_env_vars(v)
        elif isinstance(v, dict):
            result[k] = _expand_dict(v)
        else:
            result[k] = v
    return result


@dataclass
class AnthropicConfig:
    api_key: str
    default_model: str = "claude-sonnet-4-20250514"
    base_url: str | None = None


@dataclass
class OpenAICompatConfig:
    model_id: str
    base_url: str
    api_key: str


AnthropicCompatConfig = OpenAICompatConfig  # Same shape: model_id, base_url, api_key


@dataclass
class ProviderConfig:
    anthropic: AnthropicConfig | None = None
    openai_compat: dict[str, OpenAICompatConfig] = field(default_factory=dict)
    anthropic_compat: dict[str, AnthropicCompatConfig] = field(default_factory=dict)


def load_provider_config(path: Path) -> ProviderConfig:
    """Load provider config from YAML, expanding env vars."""
    if not path.exists():
        raise FileNotFoundError(f"Provider config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().replace("\t", "    ")
    raw = yaml.safe_load(text)
    expanded = _expand_dict(raw)

    config = ProviderConfig()
    if "anthropic" in expanded:
        ant = expanded["anthropic"]
        config.anthropic = AnthropicConfig(
            api_key=ant["api_key"],
            default_model=ant.get("default_model", "claude-sonnet-4-20250514"),
            base_url=ant.get("base_url"),
        )
    for alias, cfg in expanded.get("openai_compat", {}).items():
        if not isinstance(cfg, dict):
            continue
        config.openai_compat[alias] = OpenAICompatConfig(
            model_id=cfg["model_id"],
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
        )
    for alias, cfg in expanded.get("anthropic_compat", {}).items():
        if not isinstance(cfg, dict):
            continue
        config.anthropic_compat[alias] = AnthropicCompatConfig(
            model_id=cfg["model_id"],
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
        )
    return config


@dataclass
class AgentConfig:
    prompt_md: Path
    model_alias: str
    temperature: float = 0.7
    max_turns: int = 5
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.prompt_md, str):
            object.__setattr__(self, "prompt_md", Path(self.prompt_md))


def load_agent_configs(path: Path, base_dir: Path | None = None) -> dict[str, AgentConfig]:
    """Load agent configs from YAML. prompt_md paths resolved relative to base_dir."""
    if not path.exists():
        raise FileNotFoundError(f"Agent config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    configs = {}
    for name, cfg in raw.get("agents", {}).items():
        prompt_path = Path(cfg["prompt_md"])
        if base_dir and not prompt_path.is_absolute():
            prompt_path = base_dir / prompt_path
        configs[name] = AgentConfig(
            prompt_md=prompt_path,
            model_alias=cfg["model_alias"],
            temperature=cfg.get("temperature", 0.7),
            max_turns=cfg.get("max_turns", 5),
            skills=cfg.get("skills", []),
            tools=cfg.get("tools", []),
        )
    return configs


# === User Settings (config/settings.json) ===

SETTINGS_DEFAULTS: dict[str, Any] = {
    "output_dir": "",
    "sf2_path": "",
    "max_iterations": 3,
    "review_threshold": 7,
    "skip_review": False,
}


def load_settings(server_root: Path) -> dict[str, Any]:
    """Load user settings from config/settings.json, merging defaults for missing keys."""
    path = server_root / "config" / "settings.json"
    if not path.exists():
        return dict(SETTINGS_DEFAULTS)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    merged = dict(SETTINGS_DEFAULTS)
    merged.update(data)
    return merged


def save_settings(server_root: Path, settings: dict[str, Any]) -> None:
    """Write settings to config/settings.json, creating parent dirs if needed."""
    path = server_root / "config" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


_WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def sanitize_prompt_for_filename(prompt: str, max_length: int = 20) -> str:
    """Extract a filesystem-safe name from user prompt."""
    cleaned = prompt.strip()[:max_length]
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', cleaned)
    cleaned = cleaned.strip('. ')
    if not cleaned or cleaned in _WINDOWS_RESERVED or cleaned in {".", ".."}:
        return "untitled"
    return cleaned


def rename_workdir_with_title(workdir: str, title: str) -> str:
    """Rename workdir to use title instead of prompt snippet.

    Keeps the timestamp suffix intact: {old_name}_{timestamp} → {title}_{timestamp}
    Returns the new workdir path.
    """
    old_path = Path(workdir)
    if not old_path.exists():
        return workdir

    old_name = old_path.name
    # Extract timestamp suffix (last _YYYYMMDD_HHMMSS)
    sep = old_name.rfind("_")
    if sep > 0:
        timestamp = old_name[sep + 1 :]
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    new_name = f"{sanitize_prompt_for_filename(title)}_{timestamp}"
    new_path = old_path.parent / new_name

    if new_path.exists() or new_path == old_path:
        return workdir

    old_path.rename(new_path)
    logger.info("Workdir renamed: %s → %s", old_name, new_name)
    return str(new_path)


def generate_workdir(settings: dict[str, Any], session_id: str, prompt: str) -> str:
    """Generate workdir path based on settings.

    If output_dir is configured: {output_dir}/{sanitized_prompt}_{timestamp}
    If empty/missing: legacy temp dir (backward compatible)
    """
    output_dir = settings.get("output_dir", "").strip()
    if not output_dir:
        if not re.match(r'^[a-zA-Z0-9_\-]+$', session_id):
            raise ValueError(f"Invalid session_id: {session_id}")
        return str(Path(tempfile.gettempdir()) / "clef-work" / session_id)
    raw_path = Path(output_dir)
    if not raw_path.is_absolute():
        raise ValueError("output_dir must be an absolute path")
    resolved = raw_path.resolve()
    task_name = sanitize_prompt_for_filename(prompt)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    subdir = f"{task_name}_{timestamp}"
    return str(resolved / subdir)


# === Provider / Agent YAML Write-Back ===

def load_provider_config_raw(path: Path) -> dict:
    """Load provider YAML without env var expansion (for editing)."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_provider_config(path: Path, raw: dict) -> None:
    """Save provider config back to YAML, validating round-trip fidelity."""
    yaml_str = yaml.dump(raw, allow_unicode=True, default_flow_style=False)
    parsed = yaml.safe_load(yaml_str)
    if parsed is None:
        raise ValueError("YAML serialization produced invalid output")
    path.write_text(yaml_str, encoding="utf-8")


def save_agent_configs(path: Path, configs: dict[str, AgentConfig]) -> None:
    """Save agent configs back to YAML, preserving all fields."""
    raw: dict = {"agents": {}}
    for name, cfg in configs.items():
        raw["agents"][name] = {
            "prompt_md": str(cfg.prompt_md),
            "model_alias": cfg.model_alias,
            "temperature": cfg.temperature,
            "max_turns": cfg.max_turns,
            "skills": cfg.skills,
            "tools": cfg.tools,
        }
    yaml_str = yaml.dump(raw, allow_unicode=True, default_flow_style=False)
    path.write_text(yaml_str, encoding="utf-8")
