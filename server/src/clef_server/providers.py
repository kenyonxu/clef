"""LLM Provider factory — creates AF client instances from config."""

from agent_framework.anthropic import AnthropicClient

from clef_server.chat_completions_client import ChatCompletionsClient
from clef_server.config import ProviderConfig


def create_providers(config: ProviderConfig) -> dict:
    """Create client instances from ProviderConfig.

    Returns:
        Dict mapping alias → client instance.
        "anthropic" → AnthropicClient (uses AF Responses API)
        "<alias>" → ChatCompletionsClient (uses /chat/completions for compatibility)
    """
    providers: dict = {}

    if config.anthropic and config.anthropic.api_key:
        providers["anthropic"] = AnthropicClient(
            api_key=config.anthropic.api_key,
            model=config.anthropic.default_model,
        )

    for alias, cfg in config.openai_compat.items():
        if not cfg.api_key:
            continue
        providers[alias] = ChatCompletionsClient(
            model=cfg.model_id,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
        )

    return providers
