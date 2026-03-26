# Order & Exchange Configuration

> Configuration settings that affect order execution behavior.

---

## Leverage

Set in `config.yaml`:

```yaml
risk:
  leverage: 10  # 1-125 for Binance Futures
```

- Validated: 1 ≤ leverage ≤ 125
- Applied per-trade via `exchange.set_leverage(leverage, symbol)` before entry
- Affects position sizing: `max_notional = balance × max_position_size_pct × leverage`
- **Note**: `exchange.leverage` and `risk.leverage` both exist in config — `risk.leverage` is the authoritative value used by PortfolioManager

## Margin Type

```yaml
exchange:
  margin_type: 'ISOLATED'  # ISOLATED or CROSS
```

- `ISOLATED`: Each position has its own margin. Liquidation affects only that position.
- `CROSS`: All positions share margin. Higher capital efficiency but cascading liquidation risk.
- Recommendation: Use `ISOLATED` for safety.

## Fee Rates

| Mode | Taker Fee | Maker Fee | Notes |
|------|-----------|-----------|-------|
| `mock` (BacktestEngine) | 0.05% | 0.02% | Defaults from `app/core/constants.py` |
| `sim` (PaperExchange) | 0.04% | 0.02% | Defaults from `app/core/constants.py` |
| `paper` / `live` | Exchange-determined | Exchange-determined | Depends on VIP level |

## Exchange Name

```yaml
exchange:
  name: 'binanceusdm'  # binanceusdm | binance | lighter | hyperliquid
```

- `binanceusdm` and `binance` both route to `BinanceAdapter`
- Other names trigger DEX auto-discovery

## Testnet vs Mainnet

Determined by `bot.mode`:

| Mode | Network | API URL |
|------|---------|---------|
| `paper` | Testnet | `https://testnet.binancefuture.com` (set by CCXT sandbox mode) |
| `live` | Mainnet | `https://fapi.binance.com` |

Testnet has separate order books, lower liquidity, and free test funds. Behavior closely mirrors mainnet but with occasional differences in available pairs and API features.

## Precision

`BinanceAdapter.get_precision_info(symbol)` returns `(price_precision, qty_precision)` from CCXT market info. Defaults to `(2, 3)` on error. Orders are rounded to these precisions before submission.
