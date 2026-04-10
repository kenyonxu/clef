"""LLM Provider factory — creates AF client instances from config."""

# Patch OpenTelemetry Meter.create_histogram to accept advisory kwargs
# that agent_framework passes but opentelemetry-sdk doesn't yet support.
try:
    from opentelemetry.sdk.metrics._internal import Meter as _SdkMeter
    _orig = _SdkMeter.create_histogram
    def _patched_create_histogram(self, *args, **kwargs):
        kwargs.pop("explicit_bucket_boundaries_advisory", None)
        return _orig(self, *args, **kwargs)
    _SdkMeter.create_histogram = _patched_create_histogram
    # Set MeterProvider so get_meter() returns the patched SDK Meter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.metrics import set_meter_provider
    set_meter_provider(MeterProvider())
except Exception:
    pass

from agent_framework.anthropic import AnthropicClient

from clef_server.chat_completions_client import ChatCompletionsClient
from clef_server.config import ProviderConfig


def create_providers(config: ProviderConfig) -> dict:
    """Create client instances from ProviderConfig.

    Returns:
        Dict mapping alias → client instance.
        "anthropic" → AnthropicClient (uses AF Responses API)
        "<alias>" → ChatCompletionsClient or AnthropicClient
    """
    providers: dict = {}

    if config.anthropic and config.anthropic.api_key:
        providers["anthropic"] = _make_anthropic_client(
            api_key=config.anthropic.api_key,
            model=config.anthropic.default_model,
            base_url=config.anthropic.base_url,
        )

    for alias, cfg in config.openai_compat.items():
        if not cfg.api_key:
            continue
        providers[alias] = ChatCompletionsClient(
            model=cfg.model_id,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
        )

    for alias, cfg in config.anthropic_compat.items():
        if not cfg.api_key:
            continue
        providers[alias] = _make_anthropic_client(
            api_key=cfg.api_key,
            model=cfg.model_id,
            base_url=cfg.base_url,
        )

    return providers


def _make_anthropic_client(api_key: str, model: str, base_url: str | None = None) -> AnthropicClient:
    """Create an AnthropicClient, optionally with custom base_url for compatible proxies."""
    kwargs: dict = {"api_key": api_key, "model": model}
    if base_url:
        from anthropic import AsyncAnthropic
        kwargs["anthropic_client"] = AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
        )
    return AnthropicClient(**kwargs)
