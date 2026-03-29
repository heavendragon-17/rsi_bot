"""FastColumn — lightweight column proxy with .values, .min(), .max(), .sum()."""

from __future__ import annotations

from typing import Any

import numpy as np


class FastColumn:
    """Lightweight column proxy with .values, .min(), .max(), .sum()."""

    __slots__ = ("_arr", "_start", "_end")

    def __init__(self, arr: np.ndarray, start: int, end: int) -> None:
        self._arr = arr
        self._start = start
        self._end = end

    @property
    def values(self) -> np.ndarray:
        return self._arr[self._start : self._end]

    def min(self) -> Any:
        return self._arr[self._start : self._end].min()

    def max(self) -> Any:
        return self._arr[self._start : self._end].max()

    def sum(self) -> Any:
        return self._arr[self._start : self._end].sum()

    def __gt__(self, other) -> np.ndarray:
        v = self._arr[self._start : self._end]
        o = other.values if isinstance(other, FastColumn) else other
        return v > o

    def __lt__(self, other) -> np.ndarray:
        v = self._arr[self._start : self._end]
        o = other.values if isinstance(other, FastColumn) else other
        return v < o

    def __ge__(self, other) -> np.ndarray:
        v = self._arr[self._start : self._end]
        o = other.values if isinstance(other, FastColumn) else other
        return v >= o

    def __le__(self, other) -> np.ndarray:
        v = self._arr[self._start : self._end]
        o = other.values if isinstance(other, FastColumn) else other
        return v <= o

    def __len__(self) -> int:
        return self._end - self._start
