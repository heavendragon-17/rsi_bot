"""Phase 1 audit aggregator — converts a backtest run into an `AuditResult`.

`run_audit(run_id)` runs the six audit tests (sanity, bootstrap CI,
deflated Sharpe, information coefficient, PBO) over a single backtest
run and returns one structured verdict. Sub-tests whose modules aren't
yet implemented (still docstring-only stubs) report as ``None`` so the
aggregator stays usable while the rest of the pipeline is built.

Aggregate verdict: ``overall_passed = True`` iff every sub-test that
*actually ran* returned ``passed=True``. PBO is excluded from the count
when it returns ``available=False`` (no grid-search siblings).

Multi-symbol IC verdict (v1): MAJORITY of symbols clear the |IC|
threshold at >= one horizon AND no symbol is direction-mismatched.
The choice is documented in ``audit/constants.py``
(``IC_AGGREGATE_POLICY``).

This module is print-friendly: all sub-results are stored on a frozen
dataclass with a default-generated ``__repr__``. Use ``dataclasses.asdict``
when serializing to JSON.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.backtest.audit.constants import (
    IC_DIRECTION_MISMATCH_HORIZON,
    IC_MIN_ABS,
    STRATEGY_DIRECTION_SIDE,
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
    run_id: int
    overall_passed: bool
    n_tests_run: int
    n_tests_passed: int

    sanity: dict | None
    bootstrap: dict | None
    ic: dict[str, Any] | None
    dsr: Any | None
    pbo: PBOResult | None

    n_trades: int
    symbols: list[str]
    is_batch: bool
    duration_seconds: float

    direction_mismatch: dict[str, bool] | None
    reason: str | None = None


# ── sub-test runners with graceful fallback ──────────────────────────────────


def _try_run_bootstrap(tl: TradeLog) -> dict | None:
    try:
        from app.backtest.audit.bootstrap_ci import run_bootstrap_ci
    except ImportError:
        return None
    try:
        return run_bootstrap_ci(tl)
    except Exception as exc:  # noqa: BLE001 — protect aggregator from sub-test crashes
        logger.warning("audit_bootstrap_failed", run_id=tl.run_id, error=str(exc))
        return None


def _try_run_dsr(tl: TradeLog) -> Any | None:
    try:
        from app.backtest.audit.deflated_sharpe import run_dsr_analysis
    except ImportError:
        return None
    try:
        return run_dsr_analysis(tl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit_dsr_failed", run_id=tl.run_id, error=str(exc))
        return None


def _try_run_ic_per_symbol(symbols: list[str], timeframe: str) -> dict[str, Any] | None:
    try:
        from app.backtest.audit.information_coefficient import run_ic_analysis
        from app.backtest.audit.signal_panel import build_signal_panel
    except ImportError:
        return None
    out: dict[str, Any] = {}
    for symbol in symbols:
        try:
            panel = build_signal_panel(symbol, timeframe)
        except FileNotFoundError as exc:
            logger.warning("audit_ic_panel_missing", symbol=symbol, error=str(exc))
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit_ic_panel_failed", symbol=symbol, error=str(exc))
            continue
        try:
            out[symbol] = run_ic_analysis(panel)
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit_ic_run_failed", symbol=symbol, error=str(exc))
            continue
    return out or None


# ── direction inference ──────────────────────────────────────────────────────


def _infer_direction_from_trades(tl: TradeLog) -> str:
    """Return 'long' / 'short' / 'both' from realized trade sides."""
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


def _ic_value_at_horizon(symbol_ic_result: Any, horizon: int) -> float | None:
    """Best-effort extraction of the IC value at ``horizon`` from an IC result.

    The IC module hasn't been implemented yet; once it is, the result
    shape will be either a dict keyed by horizon or a dataclass with a
    ``per_horizon`` mapping. Probe both shapes; return ``None`` if the
    horizon isn't represented.
    """
    if symbol_ic_result is None:
        return None
    candidates = []
    per_h = getattr(symbol_ic_result, "per_horizon", None)
    if per_h is not None:
        candidates.append(per_h)
    if isinstance(symbol_ic_result, dict):
        candidates.append(symbol_ic_result.get("per_horizon", symbol_ic_result))
    for mapping in candidates:
        if not isinstance(mapping, dict):
            continue
        entry = mapping.get(horizon, mapping.get(str(horizon)))
        if entry is None:
            continue
        if isinstance(entry, dict):
            val = entry.get("ic")
            if val is not None:
                return float(val)
        else:
            try:
                return float(entry)
            except (TypeError, ValueError):
                continue
    return None


def _compute_direction_mismatch(
    ic_results: dict[str, Any] | None,
    direction: str,
) -> dict[str, bool] | None:
    """Per-symbol direction-vs-IC mismatch flag.

    ``True``  → direction conflicts with IC sign at ``IC_DIRECTION_MISMATCH_HORIZON``
    ``False`` → direction agrees with IC sign
    Symbols with neutral / unavailable IC are omitted from the result.
    Returns ``None`` when IC isn't available at all or the strategy is
    mixed-direction.
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


# ── IC aggregate verdict ──────────────────────────────────────────────────────


def _ic_passed_aggregate(
    ic_results: dict[str, Any] | None,
    direction_mismatch: dict[str, bool] | None,
) -> bool | None:
    """v1 majority rule: > half of symbols clear |IC| threshold AND no mismatch."""
    if not ic_results:
        return None
    passed_count = 0
    total = 0
    for res in ic_results.values():
        total += 1
        passed = getattr(res, "passed", None)
        if passed is None and isinstance(res, dict):
            passed = res.get("passed")
        if passed is None:
            best = 0.0
            per_h = getattr(res, "per_horizon", None) or (
                res.get("per_horizon") if isinstance(res, dict) else None
            )
            if isinstance(per_h, dict):
                for entry in per_h.values():
                    val = entry.get("ic") if isinstance(entry, dict) else entry
                    try:
                        best = max(best, abs(float(val)))
                    except (TypeError, ValueError):
                        continue
            passed = best >= IC_MIN_ABS
        if passed:
            passed_count += 1
    if total == 0:
        return None
    majority_clear = passed_count * 2 > total
    if direction_mismatch and any(direction_mismatch.values()):
        return False
    return majority_clear


# ── overall verdict ───────────────────────────────────────────────────────────


def _result_passed(result: Any) -> bool:
    """Read ``passed`` from a dataclass or dict result; default False."""
    val = getattr(result, "passed", None)
    if val is None and isinstance(result, dict):
        val = result.get("passed")
    return bool(val)


def _aggregate_verdict(
    *,
    sanity: dict | None,
    bootstrap: dict | None,
    dsr: Any | None,
    ic: dict[str, Any] | None,
    pbo: PBOResult | None,
    direction_mismatch: dict[str, bool] | None,
) -> tuple[bool, int, int]:
    """Return (overall_passed, n_tests_run, n_tests_passed)."""
    n_run = 0
    n_passed = 0

    if sanity is not None:
        n_run += 1
        if _result_passed(sanity):
            n_passed += 1

    if bootstrap is not None:
        n_run += 1
        if _result_passed(bootstrap):
            n_passed += 1

    if dsr is not None:
        n_run += 1
        if _result_passed(dsr):
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


# ── public entrypoint ─────────────────────────────────────────────────────────


def run_audit(
    run_id: int,
    *,
    single_direction: bool = False,
    timeframe: str = _DEFAULT_TIMEFRAME,
    session: Session | None = None,
) -> AuditResult:
    """Run all audit sub-tests for ``run_id`` and return an ``AuditResult``."""
    started = time.perf_counter()
    own_session = session is None
    db = session or SessionLocal()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if run is None:
            return AuditResult(
                run_id=run_id, overall_passed=False,
                n_tests_run=0, n_tests_passed=0,
                sanity=None, bootstrap=None, ic=None, dsr=None, pbo=None,
                n_trades=0, symbols=[], is_batch=False,
                duration_seconds=time.perf_counter() - started,
                direction_mismatch=None, reason=f"run {run_id} not found",
            )

        cfg = db.query(RunConfig).filter(RunConfig.run_id == run_id).first()
        strategy = (
            db.query(Strategy).filter(Strategy.id == run.strategy_id).first()
            if run.strategy_id is not None
            else None
        )
        cfg_timeframe = cfg.timeframe if cfg is not None else timeframe
        effective_timeframe = timeframe or cfg_timeframe

        tl = build_trade_log(run_id, session=db)
        if tl.df.empty:
            return AuditResult(
                run_id=run_id, overall_passed=False,
                n_tests_run=0, n_tests_passed=0,
                sanity=None, bootstrap=None, ic=None, dsr=None, pbo=None,
                n_trades=0, symbols=[], is_batch=bool(cfg.is_batch_mode) if cfg else False,
                duration_seconds=time.perf_counter() - started,
                direction_mismatch=None, reason="no closed trades",
            )

        symbols_traded = sorted(tl.df["symbol"].dropna().unique().tolist())
        is_batch = bool(cfg.is_batch_mode) if cfg is not None else len(symbols_traded) > 1

        sanity_result = run_sanity_audits(tl, single_direction=single_direction)
        bootstrap_result = _try_run_bootstrap(tl)
        dsr_result = _try_run_dsr(tl)
        ic_result = _try_run_ic_per_symbol(symbols_traded, effective_timeframe)
        pbo_result = run_pbo_analysis(run_id, session=db)

        direction = _resolve_strategy_direction(
            strategy.name if strategy is not None else None,
            tl,
        )
        direction_mismatch = _compute_direction_mismatch(ic_result, direction)

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
            run_id=run_id, overall_passed=overall,
            n_tests_run=n_run, n_tests_passed=n_passed,
            sanity=sanity_result,
            bootstrap=bootstrap_result,
            ic=ic_result,
            dsr=dsr_result,
            pbo=pbo_result,
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
