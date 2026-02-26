# Test Configuration

> pytest setup, markers, and CI expectations.

---

## pytest Setup

- Framework: pytest 9.0.2
- Python: 3.13 (conda env `rsi`)
- No `pytest.ini` or `pyproject.toml` pytest config — default settings

## Running Tests

```bash
# Activate environment
source C:/ProgramData/miniconda3/Scripts/activate rsi

# All tests
python -m pytest tests/ -v

# Single file
python -m pytest tests/test_partial_tp_sl.py -v

# Single test
python -m pytest tests/test_binance_adapter.py::test_name -v

# Skip integration tests
python -m pytest tests/ -v --ignore=tests/test_binance_adapter.py

# Ignore debug files with hardcoded paths
python -m pytest tests/ -v --ignore=tests/test_binance_adapter.py --ignore=tests/debug_*.py
```

## Environment Variables for Tests

| Variable | Default | Purpose |
|----------|---------|---------|
| `RUN_INTEGRATION_TESTS` | unset (disabled) | Set to `1` to enable Binance testnet integration tests |

## CI Expectations

- All unit tests should pass (except known issues in [known-test-issues.md](known-test-issues.md))
- Integration tests (`test_binance_adapter.py`) are opt-in via env var
- No external services required for unit tests (all exchange calls are mocked)
- Tests should complete within 60 seconds total
