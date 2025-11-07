from __future__ import annotations

"""
Cost utilities for approximating USD costs per provider.

Rates (USD per 1K tokens):
- groq:   0.0002
- gemini: 0.00035
- hf:     0.0004

Formula: ((tokens_in + tokens_out) / 1000.0) * rate

Note: Token estimation for missing values (e.g., HF) should be done by the caller
before invoking compute_cost. This function assumes integer token counts.
"""

from typing import Literal

BackendName = Literal["groq", "gemini", "hf"]

RATE_PER_K: dict[str, float] = {
    "groq": 0.0002,
    "gemini": 0.00035,
    "hf": 0.0004,
}


def compute_cost(backend_name: BackendName, tokens_in: int, tokens_out: int) -> float:
    """Compute approximate USD cost for a completion.

    Args:
        backend_name: one of "groq", "gemini", "hf"
        tokens_in: integer count of input tokens
        tokens_out: integer count of output tokens

    Returns:
        Approximate float cost in USD.
    """
    rate = RATE_PER_K.get(backend_name, 0.0)
    ti = max(0, int(tokens_in or 0))
    to = max(0, int(tokens_out or 0))
    total = ti + to
    return (total / 1000.0) * float(rate)
