"""Small deterministic controller serialization helpers."""
import math
import uuid


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _estimate_tokens(value: str) -> int:
    return max(1, math.ceil(len(value.encode("utf-8")) / 4))
