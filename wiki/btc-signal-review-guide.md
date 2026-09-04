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

Use the **M5**, **M15**, **H1**, and **H4** buttons in the chart header to inspect
the same signal on each native timeframe. This does not change the signal or
your saved review. When a higher timeframe did not close exactly at the signal
time, the blue message identifies the latest fully closed candle used as the
safe point-in-time anchor.

Check that:

- the signal marker is on the correct candle;
- the price chart (beige background) shows the green EMA21 and red EMA200 lines;
- the RSI pane shows black RSI21, green EMA9 RSI, and red WMA45 RSI;
- the H1 and H4 confirmation lines are marked with a green check; and
- the chart does not look broken, empty, or obviously contradictory to the
  card.

For an M5 signal, the card should show RSI21 above EMA9, EMA9 above WMA45,
RSI21 below 60, and the extra M5 checks. For an M15 signal, the card should
show EMA9 crossing above WMA45. Both timeframes require the price and H1/H4
confirmation checks.

### 5. Set the trade plan, then save your decision

Start with the **TP/SL trade plan** box beside the chart. The **Signal entry**
is read-only and is always the signal candle close. Enter both **Take profit**
and **Stop loss**, then click **Save TP/SL**. Set these levels before choosing
whether the chart is good, bad, or uncertain. The plan is stored immediately,
but future candles remain hidden until a quality label is selected.

The **Human review** bar is above the chart and trade-plan work area. Under
**1. Entry quality**, choose one:

- **Good** — the alert and chart look correct;
- **Bad** — something is clearly wrong; or
- **Uncertain** — you cannot decide.

After choosing a quality label, 2,000 future candles become available. The
chart stays zoomed around the signal so the candles remain readable; pan right
to inspect what happened. The green chart message shows how much future time
is loaded. When needed, use **Extend by 2,000 candles** at the bottom of the
chart.

Once the quality label unlocks the future, the chart draws the saved levels and
the box reports which level was touched first and how long it took, using future
candles from the signal's native timeframe. If both levels are inside the same
candle, the result is shown as ambiguous because candle data cannot prove which
wick came first.

This is not a 1R, PnL, or automatic WIN/LOSS calculation. The TP/SL result is
separate from the manual review label. You may still choose **WIN**, **LOSS**,
or **SKIP** under **2. Manual outcome** if you want to record your own human
judgment.

Write a short explanation in the notes box. Notes save automatically, and the
status line confirms when the review is saved.

The quality decision, manual outcome, and TP/SL observation are separate. A
good-looking chart can still have a bad later outcome. This screen does not
calculate trading profit or loss.

### 6. Move to the next signal

Use **Previous** and **Next signal** at the top of the detail screen. The page
also shows your position in the current queue, and **Next signal** is
highlighted after an outcome is recorded. You can go back and switch between
M5 and M15 at any time.

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

The UI bundle is committed to the repository, so `git pull` delivers it and no
build step is needed. After a frontend code change, the developer runs
`release_ui.bat` to rebuild and push the bundle. The reviewer only needs to
double-click `run_backtest_ui.bat` afterward.
