"""
Maps a logical model name — what agents, policy files, and the UI refer to
— onto a provider-specific identifier. Isolated in one module because the
two providers name models differently: the Anthropic API takes a bare model
name, while Bedrock requires a region-prefixed inference profile id
(e.g. "us.anthropic.claude-haiku-4-5-20251001-v1:0"). Adding a model means
editing this file only.
"""

from __future__ import annotations

# Anthropic API model names are already the logical name; kept as an
# explicit allowlist rather than pass-through so an unknown model fails
# fast instead of hitting the API with a typo.
ANTHROPIC_MODEL_IDS: dict[str, str] = {
    "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
    "claude-sonnet-5": "claude-sonnet-5",
    "claude-opus-5": "claude-opus-5",
}

# Bedrock inference-profile suffix per logical model; the region prefix
# ("us", "eu", "apac") is applied by resolve_bedrock_model_id.
BEDROCK_MODEL_SUFFIXES: dict[str, str] = {
    "claude-haiku-4-5-20251001": "anthropic.claude-haiku-4-5-20251001-v1:0",
    "claude-sonnet-5": "anthropic.claude-sonnet-5-v1:0",
    "claude-opus-5": "anthropic.claude-opus-5-v1:0",
}


def resolve_anthropic_model_id(logical_name: str) -> str:
    try:
        return ANTHROPIC_MODEL_IDS[logical_name]
    except KeyError:
        raise ValueError(f"no Anthropic API mapping for model {logical_name!r}") from None


def resolve_bedrock_model_id(logical_name: str, *, region_prefix: str = "us") -> str:
    try:
        suffix = BEDROCK_MODEL_SUFFIXES[logical_name]
    except KeyError:
        raise ValueError(f"no Bedrock mapping for model {logical_name!r}") from None
    return f"{region_prefix}.{suffix}"
