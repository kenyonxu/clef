"""Tests for config.py — YAML loading + env var expansion."""

import os
from pathlib import Path

import pytest
import yaml

from clef_server.config import (
    AgentConfig,
    ProviderConfig,
    ProfileInfo,
    load_agent_configs,
    load_profiles,
    load_provider_config,
    load_settings,
    save_settings,
    sanitize_prompt_for_filename,
    generate_workdir,
    save_provider_config,
    load_provider_config_raw,
    save_agent_configs,
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
        assert configs["clef-composer"].model_alias == "anthropic-opus"
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


class TestSettings:
    def test_load_settings_missing_file_returns_defaults(self, tmp_path):
        settings = load_settings(tmp_path)
        assert settings["max_iterations"] == 3
        assert settings["output_dir"] == ""
        assert settings["skip_review"] is False

    def test_save_and_load_settings_roundtrip(self, tmp_path):
        custom = {"output_dir": "E:\\Music\\Clef", "max_iterations": 5}
        save_settings(tmp_path, custom)
        loaded = load_settings(tmp_path)
        assert loaded["output_dir"] == "E:\\Music\\Clef"
        assert loaded["max_iterations"] == 5
        assert loaded["review_threshold"] == 7  # default fills in

    def test_sanitize_prompt(self):
        assert sanitize_prompt_for_filename("Hello World") == "Hello World"
        assert sanitize_prompt_for_filename('A<>B*C?D') == "ABCD"
        assert sanitize_prompt_for_filename("") == "untitled"
        long = "x" * 50
        result = sanitize_prompt_for_filename(long, max_length=20)
        assert len(result) <= 20

    def test_generate_workdir_legacy(self):
        settings = {"output_dir": ""}
        result = generate_workdir(settings, "clef-abc123", "test")
        assert "clef-work" in result
        assert "clef-abc123" in result

    def test_generate_workdir_custom(self):
        settings = {"output_dir": "E:\\Music\\Clef"}
        result = generate_workdir(settings, "clef-abc123", "Boss Battle")
        assert result.startswith("E:\\Music\\Clef")
        assert "Boss Battle" in result
        assert "untitled" not in result


class TestProviderWriteBack:
    def test_save_provider_config_roundtrip(self, tmp_path):
        path = tmp_path / "providers.yaml"
        raw = {
            "anthropic": {"api_key": "${ANTHROPIC_API_KEY}", "default_model": "claude-sonnet-4-20250514"},
            "openai_compat": {
                "deepseek": {"model_id": "test-model", "base_url": "https://api.test.com", "api_key": "${DS_KEY}"},
            },
        }
        save_provider_config(path, raw)
        loaded = load_provider_config_raw(path)
        assert loaded["anthropic"]["default_model"] == "claude-sonnet-4-20250514"
        assert loaded["openai_compat"]["deepseek"]["model_id"] == "test-model"


class TestAgentWriteBack:
    def test_save_agent_configs_preserves_all_fields(self, tmp_path):
        path = tmp_path / "agents.yaml"
        configs = {
            "clef-composer": AgentConfig(
                prompt_md=".claude/agents/clef-composer.md",
                model_alias="anthropic",
                temperature=0.9,
                skills=["melody", "abc"],
                tools=["read_file"],
            ),
        }
        save_agent_configs(path, configs)
        loaded = load_agent_configs(path)
        assert loaded["clef-composer"].model_alias == "anthropic"
        assert loaded["clef-composer"].temperature == 0.9
        assert loaded["clef-composer"].skills == ["melody", "abc"]
        assert loaded["clef-composer"].tools == ["read_file"]


class TestLoadProfiles:
    def test_load_profiles_from_yaml(self, tmp_path):
        yaml_content = {
            "profiles": {
                "test-profile": {
                    "display_name": "Test",
                    "agents": {"clef-composer": "deepseek-chat"},
                },
            }
        }
        path = tmp_path / "profiles.yaml"
        path.write_text(yaml.dump(yaml_content), encoding="utf-8")
        profiles = load_profiles(path)
        assert "test-profile" in profiles
        assert profiles["test-profile"].display_name == "Test"
        assert profiles["test-profile"].agents == {"clef-composer": "deepseek-chat"}

    def test_load_profiles_missing_file(self, tmp_path):
        profiles = load_profiles(tmp_path / "nonexistent.yaml")
        assert profiles == {}

    def test_load_profiles_partial_agents(self, tmp_path):
        """Profile that only lists some agents should not affect unlisted ones."""
        yaml_content = {
            "profiles": {
                "sparse": {
                    "display_name": "Sparse",
                    "agents": {"clef-reviewer": "deepseek-chat"},
                },
            }
        }
        path = tmp_path / "profiles.yaml"
        path.write_text(yaml.dump(yaml_content), encoding="utf-8")
        profiles = load_profiles(path)
        assert profiles["sparse"].agents == {"clef-reviewer": "deepseek-chat"}
