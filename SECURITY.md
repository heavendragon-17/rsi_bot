# Security Policy

> This public source repository can operate with real API keys and real money.
> Security controls must assume that code is visible while runtime secrets are
> never committed or exposed.

---

## Secrets Management

### Never Commit Secrets
- **`.env`** contains API keys and must NEVER be committed to version control
- `.env` is listed in `.gitignore` — verify before every commit
- Use `.env.example` as a template (contains only placeholder values)

### API Key Separation
| Key Type | Environment Variable | Risk Level |
|----------|---------------------|------------|
| Testnet API keys | `BINANCE_TESTNET_API_KEY` / `SECRET_KEY` | Low — testnet funds only |
| Mainnet API keys | `BINANCE_API_KEY` / `SECRET_KEY` | **Critical — real money** |
| Telegram bot token | `TELEGRAM_BOT_TOKEN` | Medium — can send messages |
| DEX private keys | `LIGHTER_SECRET_KEY` | **Critical — wallet access** |

### Key Rotation
- Rotate API keys periodically (recommended: every 90 days)
- Rotate immediately if a key is suspected compromised
- Binance: API Management → Delete old key → Create new key
- Update `.env` file with new keys, restart the bot

### Key Permissions (Binance)
- **Enable**: Futures trading, reading account info
- **Disable**: Spot trading, withdrawals, internal transfers
- **IP whitelist**: Restrict keys to your server's IP address

---

## Exchange Mode Safety

| Mode | Risk | Safeguards |
|------|------|------------|
| `mock` | None | In-memory only, no network calls |
| `sim` | None | Read-only WebSocket, local order simulation |
| `paper` | Low | Testnet — fake funds, real API behavior |
| `live` | **High** | Real money — double-check all config before running |

### Before Going Live
1. Test strategy thoroughly in `mock` mode (backtesting)
2. Validate with `sim` mode (live ticks, simulated fills)
3. Test with `paper` mode (real exchange API, testnet funds)
4. Only then switch to `live` mode with small position sizes
5. Verify `risk.max_position_size_pct` and `risk.leverage` are conservative

---

## Code Security Rules

### Order Safety
- All exit orders (TP, SL) MUST use `reduceOnly=True` — prevents accidental position opening
- SL orders use `stop_market` (not `limit`) — guaranteed fill on volatile moves
- `PortfolioManager` is the sole execution path — never call exchange methods directly

### Input Validation
- `AppConfig.__post_init__()` validates all config values on startup
- `RiskConfig` enforces: `0 < risk_per_trade_pct <= 0.1`, `1 <= leverage <= 125`
- Strategy params are validated against `DEFAULT_CONFIG` schema

### Sensitive Files
| File | Contains | Protected By |
|------|----------|-------------|
| `.env` | API keys, tokens | `.gitignore` |
| `config.yaml` | Trading parameters | In repo (no secrets) |
| `data/backtest.db` | Backtest results | `.gitignore` |

---

## Vulnerability Reporting

If you discover a security vulnerability:

1. **Do NOT** create a public issue
2. Use GitHub private vulnerability reporting when it is enabled, or contact
   the repository owner privately
3. Include: description of vulnerability, steps to reproduce, potential impact
4. Allow reasonable time for a fix before any disclosure

---

## Dependency Security

- Dependabot reviews GitHub Actions, Python, npm, and the pinned Docker base
  image weekly
- CI runs `pip-audit` against runtime requirements on every change and release
- Review and lock runtime dependencies before treating container builds as
  reproducible production artifacts
- Review CCXT updates carefully — exchange API changes can affect order behavior
- Monitor for CVEs in: `ccxt`, `fastapi`, `sqlalchemy`, `pydantic`

---

## Backtest API Exposure

The FastAPI backtest service has no user authentication and includes mutation
and deletion endpoints. Bind it to `127.0.0.1` by default. For remote access,
use an SSH tunnel or an authenticated TLS reverse proxy; never expose the port
directly to the internet.

## Delivery Controls

- GitHub Actions use read-only repository permissions unless the production
  promotion job must update the `production` branch.
- Third-party actions are pinned to immutable commit SHAs and updated through
  Dependabot.
- Protect `mua-tren-the-nang` with required CI checks and pull requests.
- Protect the `production` environment with an approval rule and restrict it to
  release tags.
- The host deploy gate fails closed when status is stale/missing and restores
  the previous release when candidate health verification fails.
