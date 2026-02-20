"""
Tests for the custom exception hierarchy (app/core/exceptions.py).

Verifies that:
- All exceptions are subclasses of ExchangeError
- The `original` attribute carries the wrapped exception
- Exceptions can be caught by their base type
"""
import pytest
from app.core.exceptions import (
    ExchangeError,
    InsufficientFundsError,
    OrderRejectedError,
    OrderNotFoundError,
    ConnectionError,
    RateLimitError,
    PositionError,
)


def test_exception_hierarchy():
    """All custom exceptions must inherit from ExchangeError."""
    for exc_class in (
        InsufficientFundsError,
        OrderRejectedError,
        OrderNotFoundError,
        ConnectionError,
        RateLimitError,
        PositionError,
    ):
        assert issubclass(exc_class, ExchangeError), (
            f"{exc_class.__name__} must be a subclass of ExchangeError"
        )


def test_exchange_error_inherits_exception():
    assert issubclass(ExchangeError, Exception)


def test_original_attribute_preserved():
    """The wrapped original exception must be accessible via .original."""
    cause = ValueError("underlying cause")
    err = InsufficientFundsError("not enough funds", original=cause)
    assert err.original is cause


def test_original_defaults_to_none():
    err = OrderRejectedError("bad params")
    assert err.original is None


def test_catch_by_base_type():
    """Subclass exceptions must be catchable as ExchangeError."""
    with pytest.raises(ExchangeError):
        raise RateLimitError("429 too many requests")


def test_message_preserved():
    msg = "Order 123 not found on exchange"
    err = OrderNotFoundError(msg)
    assert str(err) == msg


def test_all_six_subclasses_exist():
    """Quick smoke test that all 6 documented subclasses are importable."""
    classes = [
        InsufficientFundsError,
        OrderRejectedError,
        OrderNotFoundError,
        ConnectionError,
        RateLimitError,
        PositionError,
    ]
    assert len(classes) == 6
