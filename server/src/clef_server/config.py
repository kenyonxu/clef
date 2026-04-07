"""Configuration loading — YAML files + environment variable expansion."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _expand_env_vars(value: str) -> str:
    """Expand ${VAR} and ${VAR:-default} patterns in string."""
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        if ":-" in var_name:
            var_name, default = var_name.split(":-", 1)
            return os.environ.get(var_name, default)
        env_val = os.environ.get(var_name)
        if env_val is None:
            raise ValueError(f"Environment variable {var_name} is not set")
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


@dataclass
class OpenAICompatConfig:
    model_id: str
    base_url: str
    api_key: str


@dataclass
class ProviderConfig:
    anthropic: AnthropicConfig | None = None
    openai_compat: dict[str, OpenAICompatConfig] = field(default_factory=dict)


def load_provider_config(path: Path) -> ProviderConfig:
    """Load provider config from YAML, expanding env vars."""
    if not path.exists():
        raise FileNotFoundError(f"Provider config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    expanded = _expand_dict(raw)

    config = ProviderConfig()
    if "anthropic" in expanded:
        ant = expanded["anthropic"]
        config.anthropic = AnthropicConfig(
            api_key=ant["api_key"],
            default_model=ant.get("default_model", "claude-sonnet-4-20250514"),
        )
    for alias, cfg in expanded.get("openai_compat", {}).items():
        config.openai_compat[alias] = OpenAICompatConfig(
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
            skills=cfg.get("skills", []),
            tools=cfg.get("tools", []),
        )
    return configs
