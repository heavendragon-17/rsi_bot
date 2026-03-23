"""Backtest runner modules — batch, portfolio, and tick-replay execution modes.

Import runners directly from their modules to avoid conflicts with ``python -m``
execution (eager re-exports cause a RuntimeWarning when the module is already in
``sys.modules`` before ``runpy`` executes it).
"""


def __getattr__(name: str):
    """Lazy imports — only resolve when accessed, not at package init."""
    if name == "BatchRunner":
        from app.backtest.runners.batch_runner import BatchRunner

        return BatchRunner
    if name == "PortfolioRunner":
        from app.backtest.runners.portfolio_runner import PortfolioRunner

        return PortfolioRunner
    if name == "TickReplayRunner":
        from app.backtest.runners.tick_replay import TickReplayRunner

        return TickReplayRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["BatchRunner", "PortfolioRunner", "TickReplayRunner"]
