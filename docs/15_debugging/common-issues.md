# Common Issues

> Top issues with symptoms, causes, and solutions.

---

| # | Issue | Symptom | Cause | Solution |
|---|-------|---------|-------|----------|
| 1 | ModuleNotFoundError | `No module named 'ccxt'` | Missing dependency | `pip install -r requirements.txt` in conda env |
| 2 | API key not found | `KeyError: 'BINANCE_API_KEY'` | Missing `.env` | Copy `.env.example` to `.env`, fill in keys |
| 3 | Testnet connection refused | Connection timeout to testnet | Binance testnet down | Check testnet status, try again later |
| 4 | Position size zero | No trade entered despite signal | SL too close (`< min_sl_distance_pct`) | Increase `min_sl_distance_pct` or check SL calculation |
| 5 | Leverage not set | `OrderRejectedError` on entry | Exchange mode mismatch | Verify `bot.mode` matches credentials in `.env` |
| 6 | WebSocket drops repeatedly | Frequent `stream_disconnected` | Network or Binance issue | Check connectivity, check Binance status page |
| 7 | Backtest hangs | No progress output | Data loading issue | Check CSV exists, correct format, path is valid |
| 8 | SSE connection drops | Frontend stops receiving events | CORS or timeout | Check CORS allows `localhost:3100` or the configured origin; check FastAPI keepalive |
| 9 | Strategy not found | `KeyError` in strategy loader | Not registered | Check `loader.py` STRATEGY_MAP + run `seed_strategies()` |
| 10 | Indicators NaN | RSI/EMA values are NaN | Insufficient warmup candles | Increase `warmup_candles` (default 220) |
| 11 | "Reduce only" rejected | `OrderRejectedError` on exit | Position already closed | Hard SL fired before soft SL; `_handle_soft_sl_exit()` handles this |
| 12 | Database locked | `OperationalError: database is locked` | Concurrent SQLite access | Ensure only 1 uvicorn worker (`--workers 1`) |
| 13 | Conda env not found | `EnvironmentNotFoundError` | Wrong activation command | `source C:/ProgramData/miniconda3/Scripts/activate rsi` |
| 14 | CSV not found | Backtest fails: "file not found" or `Historical 1h CSV not found` | Required data was not downloaded; BTC signal replay also needs native H1 context | Run `python app/backtest/data/download.py --symbol BTC/USDT --timeframe 1h --days 732 --output app/backtest/data`, then pass `--h1 app/backtest/data/BTCUSDT_1h.csv` to the replay |
| 15 | Decimal conversion error | `InvalidOperation` | Float string passed to Decimal | Check data source — CSV may have malformed numbers |
| 16 | Signal replay appears stuck at 75% | Signal detection logs completion but the old UI remains at 75% for minutes | An outdated build rescans full candle frames while preparing every signal's forward metrics | Stop the old server, rebuild `ui` with `npm run build`, and restart `python run_backtest_ui.py`; the current build shows `metrics` and `saving` progress and uses indexed lookups |
| 17 | Signal replay row remains running after restart | A previous run never reaches a terminal UI state | Executor queues are process-local and the server stopped during the run | Reload the Signal Review page; the API reconciles the orphan to failed, then use **Rebuild review dataset** |
| 18 | Telegram alerts never arrive though the log says "enqueued" | `Telegram send failed ... can't parse entities: Unsupported start tag ...` warnings; M15/M5 cards missing from the channel while decision counters look healthy | Message text sent with `parse_mode="HTML"` contained a raw `<` (e.g. a static glyph like `< 60.00` or `<=` in a card template); Telegram rejects the whole message | Entity-escape every `<`/`&` in message text (formatters render `&lt;`); `TelegramBot.send_message` now retries once as plain text on entity rejection — verify with `tests/test_btc_rsi_cross_alert_formatter.py::TestHtmlEscaping` and `tests/test_telegram_bot_send_fallback.py`. Compare `btc_rsi_cross_alert_enqueued` counts against the actual channel export, not just the log |
