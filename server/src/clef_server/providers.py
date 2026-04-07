"""LLM Provider factory — creates AF client instances from config."""

from agent_framework.anthropic import AnthropicClient
from agent_framework.openai import OpenAIChatClient

from clef_server.config import ProviderConfig


def create_providers(config: ProviderConfig) -> dict:
    """Create AF client instances from ProviderConfig.

    Returns:
        Dict mapping alias → client instance.
        "anthropic" → AnthropicClient
        "<alias>" → OpenAIChatClient (for each openai_compat entry)
    """
    providers: dict = {}

    if config.anthropic:
        providers["anthropic"] = AnthropicClient(
            api_key=config.anthropic.api_key,
            model=config.anthropic.default_model,
        )

    for alias, cfg in config.openai_compat.items():
        providers[alias] = OpenAIChatClient(
            model=cfg.model_id,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
        )

    return providers
