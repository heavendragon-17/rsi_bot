"""Phase 1 audit aggregator — converts a backtest run into an `AuditResult`.

`run_audit(run_id)` runs the six audit sub-tests over a single backtest
run and returns one structured verdict:

    1. sanity         — pnl_concentration, long_short_symmetry, cost_sensitivity
    2. bootstrap      — block-bootstrap CIs on Sharpe, profit factor, win rate
    3. dsr            — Deflated Sharpe Ratio
    4. ic             — Spearman IC vs forward log-returns, per traded symbol
    5. pbo            — Probability of Backtest Overfitting (CSCV)
    6. direction-vs-IC — derived flag layered on top of the IC result

Aggregate verdict
-----------------
`overall_passed = True` iff every sub-test that *actually ran* returned
`passed=True`. PBO is excluded from the count when it returns
`available=False` (no grid-search siblings — see `pbo.py`).

Multi-symbol IC verdict (v1, `IC_AGGREGATE_POLICY = "majority"` in
`audit/constants.py`): MAJORITY of symbols clear the |IC| threshold at
≥ one horizon AND no symbol is direction-mismatched. Direction
mismatch is a separate, prominent failure mode — a strategy can clear
the IC bar while trading the wrong way on most symbols, and that's
worth flagging at the top level.
TODO(audit-ic-aggregation-v2): make the policy (any/majority/all)
configurable per-strategy or per-run.

Print-friendly: every sub-result is a frozen dataclass or plain dict,
so the default `__repr__` is informative. Use `dataclasses.asdict` for
JSON serialization once the API endpoint is wired up.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import structlog
from sqlalchemy.orm import Session

from app.backtest.audit.bootstrap_ci import run_bootstrap_ci
from app.backtest.audit.constants import (
    IC_DIRECTION_MISMATCH_HORIZON,
    STRATEGY_DIRECTION_SIDE,
)
from app.backtest.audit.deflated_sharpe import DSRResult, run_dsr_analysis
from app.backtest.audit.information_coefficient import (
    ICResult,
    TradeLevelICResult,
    run_ic_per_symbol,
    run_trade_level_ic_per_symbol,
)
from app.backtest.audit.pbo import PBOResult, run_pbo_analysis
from app.backtest.audit.sanity import run_sanity_audits
from app.backtest.audit.trade_log import TradeLog, build_trade_log
from app.core.actions import SIDE_BUY, SIDE_SELL
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import Run, RunConfig, Strategy

logger = structlog.get_logger()

_DEFAULT_TIMEFRAME = "15m"


@dataclass(frozen=True)
class AuditResult:
    """Aggregated verdict for one backtest run.

    Sub-test fields are `None` when the test could not run (e.g. PBO
    has no siblings, or an IC panel CSV is missing). `overall_passed`
    is computed only over sub-tests that ran.
    """

    run_id: int
    overall_passed: bool
    n_tests_run: int
    n_tests_passed: int

    sanity: dict | None
    bootstrap: dict | None
    ic: dict[str, ICResult] | None
    dsr: DSRResult | None
    pbo: PBOResult | None

    # Trade-level IC — informational, no pass/fail thresholds yet.
    # trade_level_ic_realized: Spearman(RSI@entry, ret_pct) per symbol
    # trade_level_ic_fwd:      Spearman(RSI@entry, fwd_logret_4) per symbol
    trade_level_ic_realized: dict[str, TradeLevelICResult] | None
    trade_level_ic_fwd: dict[str, TradeLevelICResult] | None

    n_trades: int
    symbols: list[str]
    is_batch: bool
    duration_seconds: float

    direction_mismatch: dict[str, bool] | None
    reason: str | None = None


# ── safe sub-test wrappers ──────────────────────────────────────────────────


def _safe_bootstrap(tl: TradeLog) -> dict | None:
    """Run bootstrap CI; downgrade exceptions to `None` so the audit completes."""
    try:
        return run_bootstrap_ci(tl)
    except Exception as exc:  # noqa: BLE001 — protect aggregator from sub-test crashes
        logger.warning("audit_bootstrap_failed", run_id=tl.run_id, error=str(exc))
        return None


def _safe_dsr(tl: TradeLog) -> DSRResult | None:
    """Run DSR; downgrade exceptions to `None`."""
    try:
        return run_dsr_analysis(tl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit_dsr_failed", run_id=tl.run_id, error=str(exc))
        return None


# ── direction-vs-IC mismatch ────────────────────────────────────────────────


def _infer_direction_from_trades(tl: TradeLog) -> str:
    """Return 'long' / 'short' / 'both' from realized trade sides.

    Used as a fallback when the strategy slug is not in
    `STRATEGY_DIRECTION_SIDE`. A run with trades on only one side may
    still be a `both` strategy that lacked setups on the other side,
    so this is best-effort: callers should prefer the explicit map.
    """
    sides = set(tl.df["side"].unique())
    has_buy = SIDE_BUY in sides
    has_sell = SIDE_SELL in sides
    if has_buy and has_sell:
        return "both"
    if has_buy:
        return "long"
    if has_sell:
        return "short"
    return "both"


def _resolve_strategy_direction(strategy_name: str | None, tl: TradeLog) -> str:
    if strategy_name and strategy_name in STRATEGY_DIRECTION_SIDE:
        return STRATEGY_DIRECTION_SIDE[strategy_name]
    return _infer_direction_from_trades(tl)


def _ic_value_at_horizon(result: ICResult, horizon: int) -> float | None:
    """Extract the IC value at `horizon` from an `ICResult`.

    Returns `None` if the horizon isn't represented or the IC is NaN.
    """
    entry = result.per_horizon.get(horizon)
    if entry is None:
        return None
    if math.isnan(entry.ic):
        return None
    return float(entry.ic)


def _compute_direction_mismatch(
    ic_results: dict[str, ICResult] | None,
    direction: str,
) -> dict[str, bool] | None:
    """Per-symbol direction-vs-IC flag at `IC_DIRECTION_MISMATCH_HORIZON`.

    `True`  → strategy direction conflicts with IC sign at that horizon
    `False` → strategy direction agrees with IC sign
    Symbols with neutral / unavailable IC at that horizon are omitted.
    Returns `None` when IC isn't available or the strategy is `both`.
    """
    if ic_results is None or direction == "both":
        return None
    out: dict[str, bool] = {}
    for symbol, res in ic_results.items():
        ic_val = _ic_value_at_horizon(res, IC_DIRECTION_MISMATCH_HORIZON)
        if ic_val is None or ic_val == 0.0:
            continue
        if direction == "long":
            out[symbol] = ic_val < 0.0
        elif direction == "short":
            out[symbol] = ic_val > 0.0
    return out or None


# ── verdict aggregation ─────────────────────────────────────────────────────


def _ic_passed_aggregate(
    ic_results: dict[str, ICResult] | None,
    direction_mismatch: dict[str, bool] | None,
) -> bool | None:
    """v1 majority rule: > half of symbols pass AND no mismatch."""
    if not ic_results:
        return None
    if direction_mismatch and any(direction_mismatch.values()):
        return False
    passed = sum(1 for r in ic_results.values() if r.passed)
    total = len(ic_results)
    return passed * 2 > total


def _aggregate_verdict(
    *,
    sanity: dict | None,
    bootstrap: dict | None,
    dsr: DSRResult | None,
    ic: dict[str, ICResult] | None,
    pbo: PBOResult | None,
    direction_mismatch: dict[str, bool] | None,
) -> tuple[bool, int, int]:
    """Return `(overall_passed, n_tests_run, n_tests_passed)`."""
    n_run = 0
    n_passed = 0

    if sanity is not None:
        n_run += 1
        if bool(sanity.get("passed")):
            n_passed += 1

    if bootstrap is not None:
        n_run += 1
        if bool(bootstrap.get("passed")):
            n_passed += 1

    if dsr is not None:
        n_run += 1
        if dsr.passed:
            n_passed += 1

    if ic is not None:
        n_run += 1
        if _ic_passed_aggregate(ic, direction_mismatch):
            n_passed += 1

    if pbo is not None and pbo.available:
        n_run += 1
        if pbo.passed:
            n_passed += 1

    overall = n_run > 0 and n_passed == n_run
    return overall, n_run, n_passed


# ── public entrypoint ───────────────────────────────────────────────────────


def _empty_result(
    run_id: int,
    *,
    started: float,
    is_batch: bool,
    reason: str,
) -> AuditResult:
    return AuditResult(
        run_id=run_id,
        overall_passed=False,
        n_tests_run=0,
        n_tests_passed=0,
        sanity=None,
        bootstrap=None,
        ic=None,
        dsr=None,
        pbo=None,
        trade_level_ic_realized=None,
        trade_level_ic_fwd=None,
        n_trades=0,
        symbols=[],
        is_batch=is_batch,
        duration_seconds=time.perf_counter() - started,
        direction_mismatch=None,
        reason=reason,
    )


def run_audit(
    run_id: int,
    *,
    single_direction: bool = False,
    timeframe: str = _DEFAULT_TIMEFRAME,
    session: Session | None = None,
) -> AuditResult:
    """Run all audit sub-tests for `run_id` and return an `AuditResult`.

    Parameters
    ----------
    run_id
        Backtest run primary key in the audit DB.
    single_direction
        Forwarded to `run_sanity_audits`. When `True` the
        long/short symmetry sub-check is skipped (the strategy is
        declared one-sided).
    timeframe
        Used to locate per-symbol OHLCV CSVs for the IC panel. Defaults
        to `15m`; falls through to the run's stored `RunConfig.timeframe`
        when callers pass `""` or `None` (truthy precedence).
    session
        Caller-owned SQLAlchemy session. When `None` a fresh
        `SessionLocal()` is opened and closed here.
    """
    started = time.perf_counter()
    own_session = session is None
    db = session or SessionLocal()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if run is None:
            return _empty_result(run_id, started=started, is_batch=False,
                                 reason=f"run {run_id} not found")

        cfg = db.query(RunConfig).filter(RunConfig.run_id == run_id).first()
        strategy = (
            db.query(Strategy).filter(Strategy.id == run.strategy_id).first()
            if run.strategy_id is not None
            else None
        )
        effective_timeframe = timeframe or (str(cfg.timeframe) if cfg is not None else _DEFAULT_TIMEFRAME)
        cfg_is_batch = bool(cfg.is_batch_mode) if cfg is not None else False

        tl = build_trade_log(run_id, session=db)
        if tl.df.empty:
            return _empty_result(run_id, started=started, is_batch=cfg_is_batch,
                                 reason="no closed trades")

        symbols_traded = sorted(tl.df["symbol"].dropna().unique().tolist())
        is_batch = cfg_is_batch or len(symbols_traded) > 1

        sanity_result = run_sanity_audits(tl, single_direction=single_direction)
        bootstrap_result = _safe_bootstrap(tl)
        dsr_result = _safe_dsr(tl)
        ic_result = run_ic_per_symbol(symbols_traded, effective_timeframe)
        pbo_result = run_pbo_analysis(run_id, session=db)

        direction = _resolve_strategy_direction(
            str(strategy.name) if strategy is not None else None,
            tl,
        )
        direction_mismatch = _compute_direction_mismatch(ic_result, direction)
        tl_realized, tl_fwd = run_trade_level_ic_per_symbol(
            tl, symbols_traded, effective_timeframe, direction,
        )

        overall, n_run, n_passed = _aggregate_verdict(
            sanity=sanity_result,
            bootstrap=bootstrap_result,
            dsr=dsr_result,
            ic=ic_result,
            pbo=pbo_result,
            direction_mismatch=direction_mismatch,
        )

        duration = time.perf_counter() - started
        logger.info(
            "audit_completed",
            run_id=run_id,
            overall_passed=overall,
            n_tests_run=n_run,
            n_tests_passed=n_passed,
            n_trades=int(len(tl.df)),
            n_symbols=len(symbols_traded),
            duration_seconds=duration,
        )
        return AuditResult(
            run_id=run_id,
            overall_passed=overall,
            n_tests_run=n_run,
            n_tests_passed=n_passed,
            sanity=sanity_result,
            bootstrap=bootstrap_result,
            ic=ic_result,
            dsr=dsr_result,
            pbo=pbo_result,
            trade_level_ic_realized=tl_realized,
            trade_level_ic_fwd=tl_fwd,
            n_trades=int(len(tl.df)),
            symbols=symbols_traded,
            is_batch=is_batch,
            duration_seconds=duration,
            direction_mismatch=direction_mismatch,
            reason=None,
        )
    finally:
        if own_session:
            db.close()
