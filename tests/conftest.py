"""
Test configuration and shared fixtures.

Autouse fixtures here run around every test automatically, preventing
test-to-test pollution without requiring per-test boilerplate.
"""

import pytest


@pytest.fixture(autouse=True)
def reset_indicators_global_state():
    """
    Save and restore Indicators.last after each test.

    Several tests monkey-patch Indicators.last as a class-level attribute
    (e.g. ``Indicators.last = lambda df: last``). Without cleanup this leaks
    into subsequent tests and causes spurious failures.
    """
    from app.data.indicators import Indicators

    original_last = Indicators.last
    yield
    Indicators.last = original_last


@pytest.fixture(autouse=True)
def reset_structlog_context():
    """Clear any bound structlog context variables between tests."""
    try:
        import structlog

        structlog.contextvars.clear_contextvars()
    except Exception:
        pass
    yield
    try:
        import structlog

        structlog.contextvars.clear_contextvars()
    except Exception:
        pass
