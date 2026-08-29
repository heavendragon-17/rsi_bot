# BTC Signal Review — Simple Guide

This guide is for the person reviewing the charts. You do not need to use
PowerShell, Python, Conda, Node.js, or the command line.

The app is local and safe for review. It does not place trades or send live
Telegram alerts.

## For the reviewer

### 1. Open the app

Double-click this file:

```text
run_backtest_ui.bat
```

It is in the main `rsi_bot` folder. Wait for the browser to open. If it does
not open, go to:

<http://localhost:8100>

### 2. Open BTC Signal Review

Click the checklist icon in the top bar. Its name is **BTC Signal Review**.

Do not click the normal **Backtest** button.

### 3. Open or rebuild the review dataset

The **Review dataset** card shows whether M5, M15, H1, and H4 data are ready
and the exact aligned range available for replay. You do not enter dates.

If a completed dataset already exists, the newest one opens automatically and
the list starts with signals that still need review. To rebuild it:

1. Choose **All available data** (recommended), **Latest 30 days**,
   **Latest 90 days**, or **Latest 1 year**.
2. Click **Build review dataset** or **Rebuild review dataset**.
3. Follow the named progress steps until **Dataset ready** appears.
4. Choose the replay run, then click **M5 signals** or **M15 signals**.
5. Click a signal row to open it.

If the card says data needs attention, send the displayed missing-file message
to the developer. If a completed dataset has no signals under **Needs review**,
choose another quality filter before rebuilding it.

### 4. Check the chart

Look at the **Telegram alert snapshot** and the chart. The card shows the
exact values used by the alert. You do not need to calculate them yourself.

Check that:

- the signal marker is on the correct candle;
- the price is above the yellow EMA21 line;
- the RSI lines show the bullish arrangement described in the card;
- the H1 and H4 confirmation lines are marked with a green check; and
- the chart does not look broken, empty, or obviously contradictory to the
  card.

For an M5 signal, the card should show RSI21 above EMA9, EMA9 above WMA45,
RSI21 below 60, and the extra M5 checks. For an M15 signal, the card should
show EMA9 crossing above WMA45. Both timeframes require the price and H1/H4
confirmation checks.

### 5. Save your decision

Under **Human review → Chart quality**, choose one:

- **Good** — the alert and chart look correct;
- **Bad** — something is clearly wrong; or
- **Uncertain** — you cannot decide.

After choosing a quality label, the future candles become available. Use the
chart to see what happened after the signal, then choose **WIN**, **LOSS**, or
**SKIP** under **Your market outcome**. If the result cannot be decided, use
**SKIP**.

Write a short explanation in the notes box. Notes save automatically, and the
status line confirms when the review is saved.

The quality decision and the later outcome are separate. A good-looking chart
can still have a bad later outcome. This screen does not calculate trading
profit or loss.

### 6. Move to the next signal

Use **Newer** and **Older** at the top of the detail screen. You can also go
back and switch between M5 and M15.

When finished, close the browser and the black launcher window.

## If something looks wrong

Take a screenshot and send it to the developer with the signal time. Useful
messages are:

- “The app did not open.”
- “The replay finished but there are no signals.”
- “The chart is empty or does not match the alert card.”
- “The app says data is missing.”

Do not delete `data/backtest.db`; it contains saved reviews.

## Developer setup — only once

The developer prepares the computer before handing it to the reviewer:

1. Run `setup.ps1` from the main `rsi_bot` folder.
2. Confirm these versioned files are present in `app\backtest\data\`:

   ```text
   BTCUSDT_5m.csv
   BTCUSDT_15m.csv
   BTCUSDT_1h.csv
   BTCUSDT_4h.csv
   ```

   These four canonical BTC files are intentionally committed to GitHub so a
   fresh checkout has the data needed by the reviewer. Other downloaded market
   data remains local and ignored.

3. Build the UI once:

   ```cmd
   cd /d ui
   npm ci
   npm run build
   cd /d ..
   ```

After a frontend code change, run `npm run build` again. The reviewer only
needs to double-click `run_backtest_ui.bat` afterward.
