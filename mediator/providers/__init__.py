"""
Provider factory. `MODEL_PROVIDER` selects Anthropic (local dev, default)
or Bedrock (M11 AWS deployment). This is the only place that should read
`ANTHROPIC_API_KEY` / `AWS_REGION` — construct once, inside the mediator
process, and pass the instance down. Never call this from agent code (I3).
"""

from __future__ import annotations

import os

from mediator.providers.anthropic_provider import AnthropicProvider
from mediator.providers.base import ModelProvider
from mediator.providers.bedrock_provider import BedrockProvider


def get_provider() -> ModelProvider:
    provider_name = os.environ.get("MODEL_PROVIDER", "anthropic").lower()
    if provider_name == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when MODEL_PROVIDER=anthropic")
        return AnthropicProvider(api_key=api_key)
    if provider_name == "bedrock":
        region = os.environ.get("AWS_REGION", "us-east-1")
        prefix = os.environ.get("BEDROCK_INFERENCE_PROFILE_PREFIX", "us")
        return BedrockProvider(region=region, region_prefix=prefix)
    raise ValueError(f"unknown MODEL_PROVIDER {provider_name!r}")


__all__ = ["get_provider", "ModelProvider", "AnthropicProvider", "BedrockProvider"]
