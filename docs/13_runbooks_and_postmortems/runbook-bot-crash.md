# Runbook: Bot Crash

## Severity: P1-Critical

## Symptoms
- Bot process terminated unexpectedly
- No Telegram notifications
- Open positions on exchange without active management (no SL movement, no TP sync)

## Diagnostic Steps
1. Check if process is running: `ps aux | grep main.py`
2. Check exit logs: last lines of bot output
3. Check system: OOM killer? (`dmesg | grep -i oom`), disk full? power loss?
4. Check exchange for open positions: log into Binance → Positions tab

## Resolution
1. **Check for open positions on exchange**:
   - Hard SL (`stop_market`) is already on the exchange — it will protect even without the bot
   - Soft SL will NOT trigger — only the bot manages this
   - TP limit orders are on the exchange — they will fill if price reaches them
2. **Decision**:
   - If hard SL is in place → safe to restart bot normally
   - If no hard SL → manually place a stop_market on the exchange immediately
   - If position is profitable → consider manually taking profit
3. **Restart the bot**: `python main.py`
   - `sync_from_exchange()` will detect existing positions
   - Orphan detection will log warnings for untracked positions
4. **Review crash cause**: Check logs, fix underlying issue

## Prevention
- Run under process supervisor (systemd, pm2) that auto-restarts on crash
- Hard SL on exchange provides crash protection (disaster SL at `disaster_sl_multiplier × risk distance`)
- Set up external monitoring that alerts if no Telegram messages for >30 minutes
- Keep bot logs persistent for post-crash analysis

## Escalation
- If open position has no hard SL on exchange (critical — place manually)
- If crash is caused by a code bug (investigate and fix before restarting)
