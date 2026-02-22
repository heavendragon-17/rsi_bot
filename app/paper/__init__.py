# app/paper/__init__.py
"""
Live Paper Trading (sim mode) package.

Components:
  - state.py          PaperTradeState, PaperOrder, PaperPosition, ClosedTrade
  - exchange.py       PaperExchange (IFuturesExchange — local order simulation)
  - stream_manager.py PaperTradeStreamManager (aggTrade WebSocket, 500ms sampler)
  - funding.py        PaperFundingScheduler (real Binance funding rates every 8h)
  - notifier.py       PaperTelegramNotifier (rich messages + /paper_* commands)
"""
