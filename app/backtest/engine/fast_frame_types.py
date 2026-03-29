"""
FastFrame private helpers — _FastILoc and _FastIndex.
=====================================================
Internal proxy types used by FastFrame for iloc and index access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.backtest.engine.fast_frame import FastFrame


class _FastILoc:
    """Supports ff.iloc[i] and ff.iloc[a:b]."""

    __slots__ = ("_ff",)

    def __init__(self, ff: FastFrame) -> None:
        self._ff = ff

    def __getitem__(self, key):
        ff = self._ff
        if isinstance(key, int):
            if key < 0:
                abs_idx = ff._end + key
            else:
                abs_idx = ff._start + key
            if abs_idx < ff._start or abs_idx >= ff._end:
                raise IndexError(f"iloc index {key} out of range for FastFrame of length {ff._n}")
            return ff._row(abs_idx)
        elif isinstance(key, slice):
            start, stop, step = key.indices(ff._n)
            if step != 1:
                raise ValueError("FastFrame.iloc only supports step=1 slices")
            abs_start = ff._start + start
            abs_end = ff._start + stop
            return ff._subview(abs_start, abs_end)
        raise TypeError(f"FastFrame.iloc: unsupported key type {type(key)}")


class _FastIndex:
    """Minimal index proxy supporting index[-1] and iteration."""

    __slots__ = ("_index", "_start", "_end")

    def __init__(self, index: np.ndarray, start: int, end: int) -> None:
        self._index = index
        self._start = start
        self._end = end

    def __getitem__(self, key):
        if isinstance(key, int):
            if key < 0:
                abs_idx = self._end + key
            else:
                abs_idx = self._start + key
            return self._index[abs_idx]
        raise TypeError(f"FastIndex: unsupported key type {type(key)}")

    def __len__(self) -> int:
        return self._end - self._start
