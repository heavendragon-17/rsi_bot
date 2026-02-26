# app/sim/__init__.py
"""
Local Simulation (sim mode) package.

Components:
  - state.py          SimTradeState, SimOrder, SimPosition, ClosedTrade
  - exchange.py       SimExchange (IFuturesExchange — local order simulation)
  - stream_manager.py SimTradeStreamManager (aggTrade WebSocket, 500ms sampler)
  - funding.py        SimFundingScheduler (real Binance funding rates every 8h)
  - notifier.py       (deleted — replaced by app/services/notification/telegram_notifier.py)
"""
