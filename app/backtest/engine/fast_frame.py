"""
FastFrame — Pre-extracted NumPy arrays for zero-overhead backtest access.
=========================================================================
Phase 1.2 optimization: replaces per-access pandas DataFrame overhead
with direct NumPy array indexing in the strategy hot loop.

FastFrame is created once from the full pre-computed DataFrame at backtest
start. It provides indexed access to column arrays without any pandas
overhead. Strategies use it when available, falling back to DataFrame
for complex operations (divergence detection, resampling, etc.).
"""

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
        # Convert numpy scalar to Python scalar for compatibility
        if hasattr(val, "item"):
            return val.item()
        return val

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for col, arr in self._arrays.items():
            val = arr[self._idx]
            result[col] = val.item() if hasattr(val, "item") else val
        return result


class FastFrame:
    """Pre-extracted NumPy arrays providing fast indexed access.

    Created once from the full pre-computed DataFrame. Supports the
    DataFrame access patterns used by strategies:

    - ``ff.iloc[i]`` → FastRow
    - ``ff.iloc[a:b]`` → FastFrame sub-view
    - ``ff["col"]`` → FastColumn (with .values, .min(), .max())
    - ``len(ff)``
    - ``ff.columns``
    - ``ff.empty``
    - ``ff.index``
    - ``ff.tail(n)``
    - ``"col" in ff.columns``
    """

    __slots__ = ("_arrays", "_index", "_n", "_start", "_end", "columns", "_col_set")

    def __init__(
        self,
        arrays: dict[str, np.ndarray],
        index: np.ndarray,
        start: int = 0,
        end: int | None = None,
    ) -> None:
        self._arrays = arrays
        self._index = index
        n_total = len(index)
        self._start = start
        self._end = end if end is not None else n_total
        self._n = self._end - self._start
        self.columns = list(arrays.keys())
        self._col_set = set(self.columns)

    @classmethod
    def from_dataframe(cls, df) -> FastFrame:
        """Extract all columns as contiguous numpy arrays."""
        arrays = {}
        for col in df.columns:
            arrays[col] = df[col].values
        index = df.index.values
        return cls(arrays, index, start=0, end=len(df))

    def __len__(self) -> int:
        return self._n

    @property
    def empty(self) -> bool:
        return self._n == 0

    @property
    def index(self) -> _FastIndex:
        return _FastIndex(self._index, self._start, self._end)

    @property
    def iloc(self) -> _FastILoc:
        return _FastILoc(self)

    def __getitem__(self, key: str) -> FastColumn:
        arr = self._arrays.get(key)
        if arr is None:
            raise KeyError(key)
        return FastColumn(arr, self._start, self._end)

    def tail(self, n: int) -> FastFrame:
        new_start = max(self._start, self._end - n)
        return FastFrame(self._arrays, self._index, new_start, self._end)

    def _row(self, abs_idx: int) -> FastRow:
        return FastRow(self._arrays, abs_idx, name=self._index[abs_idx])

    def _subview(self, abs_start: int, abs_end: int) -> FastFrame:
        return FastFrame(self._arrays, self._index, abs_start, abs_end)


class _FastILoc:
    """Supports ff.iloc[i] and ff.iloc[a:b]."""

    __slots__ = ("_ff",)

    def __init__(self, ff: FastFrame) -> None:
        self._ff = ff

    def __getitem__(self, key):
        ff = self._ff
        if isinstance(key, int):
            # Support negative indexing
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
