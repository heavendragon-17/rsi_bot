"""FastRow — lightweight row proxy for zero-overhead single-row access."""

from __future__ import annotations

from typing import Any

import numpy as np


class FastRow:
    """Lightweight row proxy — replaces pandas Series for single-row access.

    Supports ``row["col"]``, ``row.get("col")``, and ``row.name`` (timestamp).
    """

    __slots__ = ("_arrays", "_idx", "name")

    def __init__(self, arrays: dict[str, np.ndarray], idx: int, name: Any = None) -> None:
        self._arrays = arrays
        self._idx = idx
        self.name = name

    def __getitem__(self, key: str) -> Any:
        return self._arrays[key][self._idx]

    def get(self, key: str, default: Any = None) -> Any:
        arr = self._arrays.get(key)
        if arr is None:
            return default
        val = arr[self._idx]
        if hasattr(val, "item"):
            return val.item()
        return val

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for col, arr in self._arrays.items():
            val = arr[self._idx]
            result[col] = val.item() if hasattr(val, "item") else val
        return result
