"""LLM Provider factory — creates ChatCompletionsClient instances from config.

All providers use ChatCompletionsClient, which auto-detects API format:
- OpenAI Chat Completions (base_url contains /v1)
- Anthropic Messages API (base_url contains /anthropic)
"""

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

from clef_server.chat_completions_client import ChatCompletionsClient
from clef_server.config import ProviderConfig


def create_providers(config: ProviderConfig) -> dict:
    """Create client instances from ProviderConfig.

    Returns:
        Dict mapping alias → ChatCompletionsClient instance.
    """
    providers: dict = {}

    # Standard Anthropic (direct API)
    if config.anthropic and config.anthropic.api_key:
        base_url = config.anthropic.base_url or "https://api.anthropic.com"
        providers["anthropic"] = ChatCompletionsClient(
            model=config.anthropic.default_model,
            base_url=base_url,
            api_key=config.anthropic.api_key,
        )

    # OpenAI-compatible providers (DeepSeek, SiliconFlow, etc.)
    for alias, cfg in config.openai_compat.items():
        if not cfg.api_key:
            continue
        client = ChatCompletionsClient(
            model=cfg.model_id,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
        )
        client.rpm = cfg.rpm
        client.burst = cfg.burst
        providers[alias] = client

    # Anthropic-compatible providers (GLM via Anthropic proxy, etc.)
    for alias, cfg in config.anthropic_compat.items():
        if not cfg.api_key:
            continue
        client = ChatCompletionsClient(
            model=cfg.model_id,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
        )
        client.rpm = cfg.rpm
        client.burst = cfg.burst
        providers[alias] = client

    return providers
