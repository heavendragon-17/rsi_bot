# Deployment Checklist

Use this checklist for every production tag. The recommended environment
progression remains:

```text
mock -> sim -> paper -> live
```

Longer-term platform work is prioritized in the
[infrastructure roadmap](infrastructure-roadmap.md).

## Strategy readiness

- [ ] Backtest assumptions, fees, slippage, and data range are documented.
- [ ] Walk-forward or other out-of-sample evidence has been reviewed.
- [ ] `sim` has run against live data without unexplained position drift.
- [ ] Testnet `paper` orders, partial exits, SL replacement, and restart cleanup
      have been exercised.
- [ ] Position sizing, leverage, symbol list, and aggregate exposure are
      acceptable for the intended capital.

Numeric performance thresholds are strategy-specific; do not treat a single
Sharpe/drawdown cutoff as universal deployment approval.

## Core V2.1 signal-only rollout

Core V2.1 is advisory only and is not a paper/live trading stage.

- [ ] Run the focused Core V2.1 tests and the complete suite in the named `rsi` environment.
- [ ] Validate the locked Binance candidate files, BTC benchmark, anchored PUMP CSV, and acquisition manifests.
- [ ] Re-run the full 25-candidate point-in-time replay and compare metadata, event counts, hashes, and determinism.
- [ ] Configure only `TELEGRAM_BOT_TOKEN` and the target chat/topic; do not provision exchange trading keys or a wallet for this service.
- [ ] Start with a dedicated SQLite path and confirm silent bootstrap, exact finalized tails, and coordinator/poller readiness.
- [ ] Stop and restart against the same SQLite file; verify cursor/state parity and durable post-cursor events.
- [ ] Exercise Telegram failure/retry and outbox lease recovery, including the documented at-least-once duplicate window.
- [ ] Alert on poller death/not-ready/error, stale last success, and growing outbox queues.

Do not describe this runtime as paper trading or live trading. It has no order
adapter and cannot establish fills, PnL, win rate, or taken/skipped status.
See [Core V2.1 standalone runtime](../07_trading_strategies/signal-bot.md#core-v21-standalone-durable-runtime).

## Release preflight

- [ ] The release commit is on `mua-tren-the-nang` and the worktree is clean.
- [ ] Python tests and 70% coverage gate pass.
- [ ] Architecture, Ruff, mypy, Bandit, dependency, secret, circular-import,
      documentation, and frontend-build jobs pass.
- [ ] `python scripts/check_markdown_links.py` passes.
- [ ] `bash -n deploy/*.sh` passes.
- [ ] Configuration contains no secrets and `.env` permissions are `0600`.
- [ ] `/tmp/rsi_bot_status.json` is current and position count is understood.
- [ ] The previous healthy tag and commit are recorded for rollback.
- [ ] Release notes identify config, schema, dependency, and operational
      changes.

## Promotion

- [ ] Create an exact SemVer tag: `vMAJOR.MINOR.PATCH`.
- [ ] Confirm the Deploy workflow validates CI against that tag, not another
      branch or caller commit.
- [ ] Confirm the production environment approval, if configured.
- [ ] Confirm the production branch moved to the intended SHA.
- [ ] Watch `journalctl -u check-deploy.service` and
      `/var/log/rsi-bot-deploy.log` on the VPS.
- [ ] Confirm the host health gate reports the expected tag, commit SHA, and a
      process start time after the restart.

## Post-deploy

- [ ] `systemctl is-active rsi-bot` reports `active`.
- [ ] Market-data timestamps advance for every configured timeframe.
- [ ] Telegram startup/status commands report the new version.
- [ ] Exchange positions and local tracked positions agree.
- [ ] Error rate, reconnect activity, order rejections, and notification
      failures remain at baseline for at least 15 minutes.
- [ ] Update the changelog/release record with actual deployment evidence.

## Rollback triggers

Rollback or disable execution immediately when any of these occurs:

- the new process fails the tag/SHA/start-time health gate;
- exchange and local position state disagree;
- repeated order rejection, duplicate order, or notification delivery errors
  appear;
- market data is stale for more than twice the configured timeframe;
- loss, exposure, or error thresholds exceed the operator's predeclared limit;
- a secret, dependency vulnerability, or incorrect production configuration
  is discovered.

The host deployment script automatically restores the previous source,
dependencies, `VERSION`, and service when candidate health fails. If automatic
rollback is unavailable or unhealthy, stop live execution and follow the
[VPS recovery guidance](vps-deployment-guide.md#10-troubleshooting).
