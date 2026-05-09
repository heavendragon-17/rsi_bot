"""Probability of Backtest Overfitting via Combinatorially Symmetric
Cross-Validation (Bailey, Borwein, Lopez de Prado, Zhu 2014).

Estimates the probability that the parameter set chosen as best
in-sample will rank below the median out-of-sample. Reference paper in
``docs/17_audit/references/``.

PBO requires sibling runs from a grid search. Until ``grid_search_parent_id``
is populated by the runner, this module returns ``available=False`` on all
real runs. The synthetic test case in the test suite verifies the CSCV
computation is correct.

V1 simplification: per-trade returns are aligned positionally and shorter
columns are padded with zeros up to the longest column. Better alignment
(by timestamp, or fixed time bins) is deferred to v2.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import log

import numpy as np
import structlog
from sqlalchemy.orm import Session

from app.backtest.audit.constants import PBO_BLOCK_COUNT, PBO_FAIL_THRESHOLD
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import Run, Trade

logger = structlog.get_logger()

_NO_SIBLINGS_REASON = "no sibling runs from grid search"
_LOGIT_EPSILON = 1e-12


@dataclass(frozen=True)
class PBOResult:
    available: bool
    pbo: float | None
    n_strategies: int
    n_blocks: int
    n_combinations: int
    passed: bool
    threshold: float
    reason: str | None


def _find_sibling_runs(parent_run_id: int, *, session: Session) -> list[int]:
    """Return run IDs whose ``grid_search_parent_id == parent_run_id``.

    Excludes the parent itself. Returns ``[]`` when the column does not
    exist on the model (defensive against pre-migration databases) or
    when no children rows exist.
    """
    if not hasattr(Run, "grid_search_parent_id"):
        return []
    rows = (
        session.query(Run.id)
        .filter(Run.grid_search_parent_id == parent_run_id)
        .filter(Run.id != parent_run_id)
        .all()
    )
    return [int(r[0]) for r in rows]


def _build_returns_matrix(
    sibling_run_ids: list[int],
    parent_run_id: int,
    *,
    session: Session,
) -> tuple[np.ndarray, list[int]]:
    """Build a ``(T, N)`` returns matrix from per-trade ``pnl`` values.

    Columns are ordered by run id (parent first, then siblings ascending).
    Runs that produced no closed trades are dropped; their ids are not
    in ``valid_run_ids``. Shorter columns are zero-padded to the longest
    column length — this is the v1 approximation noted in the module
    docstring.
    """
    candidate_ids = [parent_run_id] + sorted(sibling_run_ids)
    columns: list[np.ndarray] = []
    valid: list[int] = []
    for rid in candidate_ids:
        rows = (
            session.query(Trade.pnl)
            .filter(Trade.run_id == rid)
            .filter(Trade.exit_time.isnot(None))
            .order_by(Trade.entry_time.asc())
            .all()
        )
        vals = np.array(
            [float(r[0]) for r in rows if r[0] is not None],
            dtype=np.float64,
        )
        if vals.size == 0:
            continue
        columns.append(vals)
        valid.append(rid)

    if not columns:
        return np.empty((0, 0), dtype=np.float64), []
    T = max(c.size for c in columns)
    matrix = np.zeros((T, len(columns)), dtype=np.float64)
    for j, col in enumerate(columns):
        matrix[: col.size, j] = col
    return matrix, valid


def _block_sharpe(
    block_sums: np.ndarray,
    block_sumsq: np.ndarray,
    block_size: int,
    block_mask: np.ndarray,
) -> np.ndarray:
    """Sharpe per strategy on the masked-in blocks.

    ``block_sums``, ``block_sumsq`` are shape ``(S, N)``; ``block_mask``
    is shape ``(S,)`` boolean. Returns a length-``N`` array; strategies
    with zero variance over the selected blocks get a Sharpe of 0.
    """
    n = float(block_mask.sum() * block_size)
    s = block_sums[block_mask].sum(axis=0)
    sq = block_sumsq[block_mask].sum(axis=0)
    mean = s / n
    var = sq / n - mean * mean
    var = np.maximum(var, 0.0)  # guard fp negatives near zero
    std = np.sqrt(var)
    return np.where(std > 0.0, mean / std, 0.0)


def _cscv(returns_matrix: np.ndarray, n_blocks: int) -> tuple[float, int]:
    """Core CSCV computation. Returns ``(pbo, n_combinations)``.

    Steps:
      1. Trim ``T`` to be divisible by ``n_blocks`` and reshape into
         per-block sum / sum-of-squares matrices.
      2. Enumerate all ``C(n_blocks, n_blocks/2)`` IS/OOS splits.
      3. For each split, find the IS Sharpe winner, locate its OOS
         rank among the ``N`` strategies, logit-transform the relative
         rank, and accumulate.
      4. PBO = fraction of logits below zero.
    """
    if n_blocks % 2 != 0:
        raise ValueError(f"n_blocks must be even (got {n_blocks})")
    T, N = returns_matrix.shape
    if N < 2:
        raise ValueError(f"need at least 2 strategies (got {N})")
    if T < n_blocks:
        raise ValueError(f"need T >= n_blocks (got T={T}, n_blocks={n_blocks})")

    block_size = T // n_blocks
    usable = block_size * n_blocks
    M = returns_matrix[:usable, :]
    blocks = M.reshape(n_blocks, block_size, N)
    block_sums = blocks.sum(axis=1)
    block_sumsq = (blocks * blocks).sum(axis=1)

    half = n_blocks // 2
    n_strategies_plus_one = float(N + 1)

    logit_below_zero = 0
    n_total = 0
    for is_blocks in combinations(range(n_blocks), half):
        mask = np.zeros(n_blocks, dtype=bool)
        mask[list(is_blocks)] = True

        is_sharpe = _block_sharpe(block_sums, block_sumsq, block_size, mask)
        oos_sharpe = _block_sharpe(block_sums, block_sumsq, block_size, ~mask)

        winner = int(np.argmax(is_sharpe))
        winner_oos = oos_sharpe[winner]
        # Average rank treats ties symmetrically: rank in [1, N].
        n_below = int((oos_sharpe < winner_oos).sum())
        n_equal = int((oos_sharpe == winner_oos).sum())
        rank = n_below + 0.5 * (n_equal + 1)

        omega = rank / n_strategies_plus_one
        omega = min(max(omega, _LOGIT_EPSILON), 1.0 - _LOGIT_EPSILON)
        logit = log(omega / (1.0 - omega))
        if logit < 0.0:
            logit_below_zero += 1
        n_total += 1

    pbo = float(logit_below_zero) / float(n_total)
    return pbo, n_total


def _unavailable(
    *,
    n_strategies: int,
    n_blocks: int,
    threshold: float,
    reason: str,
) -> PBOResult:
    return PBOResult(
        available=False,
        pbo=None,
        n_strategies=n_strategies,
        n_blocks=n_blocks,
        n_combinations=0,
        passed=False,
        threshold=threshold,
        reason=reason,
    )


def run_pbo_analysis(
    run_id: int,
    *,
    n_blocks: int = PBO_BLOCK_COUNT,
    threshold: float = PBO_FAIL_THRESHOLD,
    session: Session | None = None,
) -> PBOResult:
    """Run PBO analysis for ``run_id`` using its grid-search siblings.

    Resolution rules:
      * If the run has ``grid_search_parent_id`` set, treat that as the
        grid-search parent and pull all of its children.
      * Otherwise treat ``run_id`` itself as the prospective parent and
        pull its children.
      * If neither path produces siblings, return
        ``available=False`` with reason "no sibling runs from grid search".
    """
    own_session = session is None
    db = session or SessionLocal()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if run is None:
            return _unavailable(
                n_strategies=0, n_blocks=n_blocks, threshold=threshold,
                reason=f"run {run_id} not found",
            )

        parent_id_attr = getattr(run, "grid_search_parent_id", None)
        parent_run_id = int(parent_id_attr) if parent_id_attr is not None else int(run_id)
        siblings = _find_sibling_runs(parent_run_id, session=db)
        if not siblings:
            return _unavailable(
                n_strategies=0, n_blocks=n_blocks, threshold=threshold,
                reason=_NO_SIBLINGS_REASON,
            )

        matrix, valid_ids = _build_returns_matrix(siblings, parent_run_id, session=db)
        n_strategies = matrix.shape[1] if matrix.size else 0
        if n_strategies < 2:
            return _unavailable(
                n_strategies=n_strategies, n_blocks=n_blocks, threshold=threshold,
                reason="need at least 2 strategies with non-empty trade history",
            )
        if matrix.shape[0] < n_blocks:
            return _unavailable(
                n_strategies=n_strategies, n_blocks=n_blocks, threshold=threshold,
                reason=f"need at least {n_blocks} trades per strategy (have {matrix.shape[0]})",
            )

        pbo, n_combinations = _cscv(matrix, n_blocks)
        logger.info(
            "audit_pbo_computed",
            run_id=run_id,
            parent_run_id=parent_run_id,
            n_strategies=n_strategies,
            n_blocks=n_blocks,
            n_combinations=n_combinations,
            pbo=pbo,
            valid_run_ids=valid_ids,
        )
        return PBOResult(
            available=True,
            pbo=pbo,
            n_strategies=n_strategies,
            n_blocks=n_blocks,
            n_combinations=n_combinations,
            passed=pbo < threshold,
            threshold=threshold,
            reason=None,
        )
    finally:
        if own_session:
            db.close()
