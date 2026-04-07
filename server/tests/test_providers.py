"""Tests for providers.py — LLM client factory."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from clef_server.config import ProviderConfig, AnthropicConfig, OpenAICompatConfig
from clef_server.providers import create_providers


class TestCreateProviders:
    def test_creates_anthropic_client(self):
        config = ProviderConfig(
            anthropic=AnthropicConfig(api_key="test-key", default_model="claude-sonnet-4-20250514"),
        )
        with patch("clef_server.providers.AnthropicClient") as mock_cls:
            providers = create_providers(config)
            mock_cls.assert_called_once_with(
                api_key="test-key",
                model="claude-sonnet-4-20250514",
            )
            assert "anthropic" in providers

    def test_creates_openai_compat_client(self):
        config = ProviderConfig(
            openai_compat={
                "deepseek": OpenAICompatConfig(
                    model_id="deepseek-chat",
                    base_url="https://api.deepseek.com/v1",
                    api_key="ds-key",
                ),
            },
        )
        with patch("clef_server.providers.OpenAIChatClient") as mock_cls:
            providers = create_providers(config)
            mock_cls.assert_called_once_with(
                model="deepseek-chat",
                base_url="https://api.deepseek.com/v1",
                api_key="ds-key",
            )
            assert "deepseek" in providers

    def test_creates_multiple_openai_compat_clients(self):
        config = ProviderConfig(
            openai_compat={
                "deepseek": OpenAICompatConfig(model_id="deepseek-chat", base_url="https://api.deepseek.com/v1", api_key="k1"),
                "glm": OpenAICompatConfig(model_id="glm-4", base_url="https://open.bigmodel.cn/api/paas/v4", api_key="k2"),
            },
        )
        with patch("clef_server.providers.OpenAIChatClient") as mock_cls:
            providers = create_providers(config)
            assert mock_cls.call_count == 2
            assert "deepseek" in providers
            assert "glm" in providers

    def test_empty_config_returns_empty(self):
        config = ProviderConfig()
        providers = create_providers(config)
        assert providers == {}
