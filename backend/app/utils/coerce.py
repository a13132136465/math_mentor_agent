"""Coerce loosely-typed values from MongoDB / LLM JSON into numeric types."""
from __future__ import annotations


def as_int(value: object, default: int = 0, lo: int | None = None, hi: int | None = None) -> int:
    try:
        n = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        n = default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
