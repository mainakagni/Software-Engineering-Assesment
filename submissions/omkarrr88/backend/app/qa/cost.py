"""Estimated cost of an answer at the paid-tier list prices in the settings."""

import math

from app.config import Settings


def estimate_tokens(text: str) -> int:
    """Rough token count (about four characters per token), used where the API reports none."""
    return math.ceil(len(text) / 4)


def estimate_cost_usd(
    *,
    prompt_tokens: int,
    output_tokens: int,
    thinking_tokens: int,
    embedding_tokens: int,
    settings: Settings,
) -> float:
    # Thinking tokens are billed as output tokens.
    micro_dollars = (
        prompt_tokens * settings.llm_input_price_per_mtok
        + (output_tokens + thinking_tokens) * settings.llm_output_price_per_mtok
        + embedding_tokens * settings.embedding_price_per_mtok
    )
    return round(micro_dollars / 1_000_000, 8)
