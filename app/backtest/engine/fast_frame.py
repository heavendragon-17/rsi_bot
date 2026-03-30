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

import numpy as np

from app.backtest.engine.fast_column import FastColumn
from app.backtest.engine.fast_frame_types import _FastILoc, _FastIndex
from app.backtest.engine.fast_row import FastRow


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
