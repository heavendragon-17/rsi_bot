# Security

> Secrets management, API key safety, and trading-specific security concerns.

---

## Secrets Management

- **`.env`** contains all API keys — NEVER commit to version control
- `.env` is in `.gitignore` — verify before every commit
- Use `.env.example` as template (placeholder values only)
- Never log or print API keys (structlog doesn't expose env vars by default)

## API Key Permissions (Binance)

| Permission | Recommended |
|-----------|-------------|
| Futures trading | Enable |
| Read account info | Enable |
| Spot trading | **Disable** |
| Withdrawals | **Disable** |
| Internal transfers | **Disable** |
| IP whitelist | **Enable** — restrict to server IP |

## Key Rotation

- Rotate every 90 days (recommended)
- Rotate immediately if compromise suspected
- Binance: API Management → Delete old → Create new → Update `.env` → Restart bot

## Order Safety

- All exit orders use `reduceOnly=True` — prevents accidental position opening
- SL uses `stop_market` (not `limit`) — guaranteed fill on volatile moves
- `PortfolioManager` is sole execution path — never bypass

## Trading-Specific Risks

| Risk | Mitigation |
|------|-----------|
| Testnet keys in live mode | Adapter enforces testnet-only keys for paper mode |
| Excessive leverage | Config validation: 1 ≤ leverage ≤ 125 |
| Risk too high | Config validation: 0 < risk_per_trade_pct ≤ 0.1 (10% max) |
| Liquidation | ISOLATED margin, conservative position sizing |

See also: `SECURITY.md` at project root for full security policy.
