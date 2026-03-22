"""
Application-level exceptions.
Each exchange adapter catches its own library errors and re-raises as these.
"""


class ExchangeError(Exception):
    """Base exception for all exchange operations."""

    def __init__(self, message: str, original: Exception = None):
        super().__init__(message)
        self.original = original


class InsufficientFundsError(ExchangeError):
    """Not enough balance/margin to execute the order."""

    pass


class OrderRejectedError(ExchangeError):
    """Exchange rejected the order (invalid params, symbol not found, etc.)."""

    pass


class OrderNotFoundError(ExchangeError):
    """Order ID does not exist on the exchange."""

    pass


class ConnectionError(ExchangeError):
    """Network/connection failure to exchange."""

    pass


class RateLimitError(ExchangeError):
    """Exchange rate limit exceeded."""

    pass


class PositionError(ExchangeError):
    """Error related to position operations (leverage, margin mode, etc.)."""

    pass
