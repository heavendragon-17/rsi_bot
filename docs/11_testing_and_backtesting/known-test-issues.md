# Known Test Issues

> Pre-existing test failures and their reasons. These are not regressions.

---

## `test_soft_sl.py` / `test_soft_sl_noretest.py`

**Status**: Failing — uses old mutable context API

**Cause**: These tests were written before the PR6 stateless strategy migration. They use `strategy.context.transition()` instead of passing `context=ContextSnapshot(...)` as a parameter.

**Additional issue**: The `pending_candle_sl` mechanism changed behavior — what was previously a direct close is now a 2-candle pattern (flag on candle N, exit on candle N+1 open).

**Fix needed**: Rewrite tests to:
1. Pass `position=PositionSnapshot(...)` and `context=ContextSnapshot(...)` params
2. Update expected behavior for 2-candle SL pattern
3. Patch `Indicators.last` explicitly

---

## `test_binance_adapter.py`

**Status**: Skipped locally — needs real API keys

**Cause**: Integration tests that call the actual Binance testnet API. Require `BINANCE_TESTNET_API_KEY` and `BINANCE_TESTNET_SECRET_KEY` in `.env`.

**Guard**: Set `RUN_INTEGRATION_TESTS=1` in `.env` to enable. Tests are skipped by default.

**Expected locally**: Errors/skips are normal without API keys configured.

---

## General Notes

- Debug/quick test files may have hardcoded paths — use `--ignore` if they fail
- Always run with conda env activated: `source C:/ProgramData/miniconda3/Scripts/activate rsi`
