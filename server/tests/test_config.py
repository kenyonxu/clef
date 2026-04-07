"""Tests for config.py — YAML loading + env var expansion."""

import os
from pathlib import Path

import pytest
import yaml

from clef_server.config import (
    AgentConfig,
    ProviderConfig,
    load_agent_configs,
    load_provider_config,
    _expand_env_vars,
)


class TestExpandEnvVars:
    def test_expands_env_var(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "secret123")
        result = _expand_env_vars("${TEST_KEY}")
        assert result == "secret123"

    def test_expands_env_var_in_string(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "secret123")
        result = _expand_env_vars("prefix_${TEST_KEY}_suffix")
        assert result == "prefix_secret123_suffix"

    def test_no_env_var_pattern(self):
        result = _expand_env_vars("plain_string")
        assert result == "plain_string"

    def test_missing_env_var_returns_empty(self):
        result = _expand_env_vars("${MISSING_KEY}")
        assert result == ""

    def test_missing_env_var_with_default(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        result = _expand_env_vars("${MISSING_KEY:-default_val}")
        assert result == "default_val"


class TestProviderConfig:
    def test_load_provider_config(self, project_root: Path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant-key")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-ds-key")
        monkeypatch.setenv("GLM_API_KEY", "test-glm-key")
        config = load_provider_config(project_root / "server" / "config" / "providers.yaml.example")
        assert config.anthropic.api_key == "test-ant-key"
        assert config.anthropic.default_model == "claude-sonnet-4-20250514"
        assert "deepseek" in config.openai_compat
        assert config.openai_compat["deepseek"].model_id == "deepseek-chat"
        assert config.openai_compat["deepseek"].api_key == "test-ds-key"
        assert config.openai_compat["glm"].model_id == "glm-4"
        assert config.openai_compat["glm"].api_key == "test-glm-key"

    def test_load_provider_config_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_provider_config(Path("/nonexistent/providers.yaml"))


class TestAgentConfigs:
    def test_load_agent_configs(self, project_root: Path):
        configs = load_agent_configs(project_root / "server" / "config" / "agents.yaml")
        assert "clef-composer" in configs
        assert configs["clef-composer"].model_alias == "deepseek"
        assert configs["clef-composer"].temperature == 0.8
        assert "melody" in configs["clef-composer"].skills
        assert "validate_abc" in configs["clef-composer"].tools

    def test_agent_config_dataclass(self):
        cfg = AgentConfig(
            prompt_md="test.md",
            model_alias="deepseek",
            temperature=0.8,
            skills=["melody", "abc"],
            tools=["read_file", "write_file"],
        )
        assert cfg.prompt_md == Path("test.md")
        assert cfg.temperature == 0.8
