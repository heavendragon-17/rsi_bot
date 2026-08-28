"""Tests for the offline BTC RSI alert replay and Markdown audit log."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from btc_alert_fixtures import (
    BASE,
    h4_close_times,
    h4_price_above_ema21_closes,
    qualifying_m5_trigger,
    qualifying_trigger,
)

import app.backtest.signal_replay as signal_replay
from app.backtest.signal_replay import (
    SignalReplayInputError,
    render_replay_markdown,
    run_btc_alert_replay,
)
from app.trading.strategy.btc_rsi_cross_alert.models import BtcRsiCrossDecision

STORAGE_SHIFT = timedelta(hours=7)


def _write_ohlcv_csv(
    path,
    close_times: list[datetime],
    closes: list[float],
    step: timedelta,
) -> None:
    frame = pd.DataFrame(
        {
            "timestamp": [
                (close_time - step + STORAGE_SHIFT).replace(tzinfo=None)
                for close_time in close_times
            ],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1.0] * len(closes),
        }
    )
    frame.to_csv(path, index=False)


def _write_qualifying_csvs(tmp_path):
    m5_end = BASE.replace(hour=9, minute=45)
    m15_end = BASE.replace(hour=10, minute=0)
    h4_end = BASE.replace(hour=8)
    m5_times, m5_closes = qualifying_m5_trigger(timedelta(minutes=5), m5_end)
    m15_times, m15_closes = qualifying_trigger(timedelta(minutes=15), m15_end)
    h4_times = h4_close_times(h4_end)
    h4_closes = h4_price_above_ema21_closes()

    m5_path = tmp_path / "BTCUSDT_5m.csv"
    m15_path = tmp_path / "BTCUSDT_15m.csv"
    h4_path = tmp_path / "BTCUSDT_4h.csv"
    _write_ohlcv_csv(m5_path, m5_times, m5_closes, timedelta(minutes=5))
    _write_ohlcv_csv(m15_path, m15_times, m15_closes, timedelta(minutes=15))
    _write_ohlcv_csv(h4_path, h4_times, h4_closes, timedelta(hours=4))
    return m5_path, m15_path, h4_path


class TestBtcAlertReplay:
    def test_replays_both_timeframes_with_full_telegram_card(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        output_path = tmp_path / "replay.md"
        generated_at = datetime(2026, 8, 28, 18, 30, tzinfo=UTC)

        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 40),
            end_utc7=datetime(2026, 8, 24, 17, 10),
            output_path=output_path,
            generated_at_utc7=generated_at,
        )

        assert {signal.timeframe for signal in result.signals} == {"5m", "15m"}
        assert [signal.sequence for signal in result.signals] == [1, 2]
        assert result.signals[0].data.trigger_close_time < result.signals[1].data.trigger_close_time

        body = output_path.read_text(encoding="utf-8")
        assert "# BTC RSI Cross Alert — Historical Replay" in body
        assert "Data window: 2026-08-24 16:40:00 UTC+7 → 2026-08-24 17:10:00 UTC+7" in body
        assert "Generated: 2026-08-29 01:30:00 UTC+7" in body
        assert "Automated win rate: NOT CALCULATED" in body
        assert "Manual review: UNREVIEWED" in body
        assert "Chart result: [ ] WIN   [ ] LOSS   [ ] SKIP" in body

        m5_card = next(signal.telegram_card for signal in result.signals if signal.timeframe == "5m")
        assert "🟢 BTC RSI BULLISH ALIGNMENT" in m5_card
        assert "Timeframe: 5m" in m5_card
        assert "Candle close: 2026-08-24 16:40:00 UTC+7" in m5_card
        assert "BTC close:" in m5_card
        assert "M5 EMA21(price):" in m5_card
        assert "M5 close > EMA21(price):" in m5_card
        assert "Current M5 RSI21:" in m5_card
        assert "Current M5 EMA9(RSI21):" in m5_card
        assert "Current M5 WMA45(RSI21):" in m5_card
        assert "M5 RSI alignment:" in m5_card
        assert "M5 EMA9(RSI21) - WMA45(RSI21):" in m5_card
        assert "M5 WMA45(RSI21) > 45.00:" in m5_card
        assert "H4 close:" in m5_card
        assert "H4 EMA21(price):" in m5_card
        assert "H4 close > EMA21(price):" in m5_card
        assert "Duplicate check: NEW event ✅" in m5_card
        assert "Event:" in m5_card

        m15_card = next(signal.telegram_card for signal in result.signals if signal.timeframe == "15m")
        assert "🟢 BTC RSI BULLISH CROSS" in m15_card
        assert "Timeframe: 15m" in m15_card
        assert "Candle close: 2026-08-24 17:00:00 UTC+7" in m15_card
        assert "BTC close:" in m15_card
        assert "M15 EMA21(price):" in m15_card
        assert "M15 close > EMA21(price):" in m15_card
        assert "Previous M15 EMA9(RSI21):" in m15_card
        assert "Previous M15 WMA45(RSI21):" in m15_card
        assert "Fresh bullish cross:" in m15_card
        assert "Current M15 RSI21:" in m15_card
        assert "Current M15 EMA9(RSI21):" in m15_card
        assert "Current M15 WMA45(RSI21):" in m15_card
        assert "H4 close:" in m15_card
        assert "H4 EMA21(price):" in m15_card
        assert "H4 close > EMA21(price):" in m15_card
        assert "Duplicate check: NEW event ✅" in m15_card
        assert "Event:" in m15_card
        assert "M15 close > EMA21(price):" in m15_card

    def test_naive_csv_open_is_shifted_once_and_rendered_in_utc_plus_7(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        output_path = tmp_path / "replay.md"
        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 40),
            end_utc7=datetime(2026, 8, 24, 17, 10),
            output_path=output_path,
            generated_at_utc7=datetime(2026, 8, 28, 0, tzinfo=UTC),
        )

        assert result.signals[0].data.trigger_close_time == datetime(
            2026, 8, 24, 9, 40, tzinfo=UTC
        )
        assert "UTC+7" in output_path.read_text(encoding="utf-8")
        assert "2026-08-24 16:40:00 UTC+7" in output_path.read_text(encoding="utf-8")

    def test_indicator_warmup_is_kept_before_requested_start(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 45),
            end_utc7=datetime(2026, 8, 24, 16, 45),
            output_path=tmp_path / "warmup.md",
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        assert [signal.timeframe for signal in result.signals] == ["5m"]
        assert result.counts.m5_candidates == 1
        assert result.counts.m15_candidates == 1
        assert result.counts.m15_rejected == 1
        assert result.counts.m5_not_ready == 0

    def test_future_rows_do_not_change_an_earlier_replay(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        baseline_path = tmp_path / "baseline.md"
        baseline = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 40),
            end_utc7=datetime(2026, 8, 24, 17, 10),
            output_path=baseline_path,
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        def append_future(path, timestamp, close):
            frame = pd.read_csv(path)
            frame.loc[len(frame)] = [timestamp, close, close, close, close, 1.0]
            frame.to_csv(path, index=False)

        append_future(m5_path, "2026-08-25 12:00:00", 999999.0)
        append_future(m15_path, "2026-08-25 12:00:00", 999999.0)
        append_future(h4_path, "2026-08-25 12:00:00", 999999.0)

        future_path = tmp_path / "future.md"
        future = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 40),
            end_utc7=datetime(2026, 8, 24, 17, 10),
            output_path=future_path,
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        assert [signal.telegram_card for signal in baseline.signals] == [
            signal.telegram_card for signal in future.signals
        ]

    def test_m5_cooldown_suppresses_only_intermediate_confirmations(self, tmp_path, monkeypatch):
        close_times = [
            BASE.replace(hour=9, minute=minute) for minute in (0, 5, 10, 15)
        ]
        m5_path = tmp_path / "m5.csv"
        m15_path = tmp_path / "m15.csv"
        h4_path = tmp_path / "h4.csv"
        _write_ohlcv_csv(m5_path, close_times, [100.0] * 4, timedelta(minutes=5))
        _write_ohlcv_csv(m15_path, [BASE.replace(hour=1)], [100.0], timedelta(minutes=15))
        _write_ohlcv_csv(h4_path, [BASE.replace(hour=0)], [100.0], timedelta(hours=4))

        def fake_prepare(event, *_frames):
            decision = BtcRsiCrossDecision(
                should_alert=True,
                event_id=f"event-{event.close_time.minute}",
                reason="TEST_ALERT",
            )
            return object(), decision, "READY"

        monkeypatch.setattr(signal_replay, "_prepare_and_evaluate", fake_prepare)
        monkeypatch.setattr(
            signal_replay,
            "format_btc_rsi_cross_alert",
            lambda _data, event_id: f"Event: {event_id}",
        )

        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 0),
            end_utc7=datetime(2026, 8, 24, 16, 20),
            output_path=tmp_path / "cooldown.md",
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        assert len(result.signals) == 2
        assert result.counts.m5_cooldown_suppressed == 2
        assert [signal.decision.event_id for signal in result.signals] == ["event-0", "event-15"]

    def test_duplicate_event_ids_are_suppressed_before_cooldown(self, tmp_path, monkeypatch):
        close_times = [BASE.replace(hour=9, minute=minute) for minute in (0, 5)]
        m5_path = tmp_path / "m5.csv"
        m15_path = tmp_path / "m15.csv"
        h4_path = tmp_path / "h4.csv"
        _write_ohlcv_csv(m5_path, close_times, [100.0] * 2, timedelta(minutes=5))
        _write_ohlcv_csv(m15_path, [BASE.replace(hour=1)], [100.0], timedelta(minutes=15))
        _write_ohlcv_csv(h4_path, [BASE.replace(hour=0)], [100.0], timedelta(hours=4))

        def fake_prepare(_event, *_frames):
            decision = BtcRsiCrossDecision(
                should_alert=True,
                event_id="same-event",
                reason="TEST_ALERT",
            )
            return object(), decision, "READY"

        monkeypatch.setattr(signal_replay, "_prepare_and_evaluate", fake_prepare)
        monkeypatch.setattr(
            signal_replay,
            "format_btc_rsi_cross_alert",
            lambda _data, event_id: f"Event: {event_id}",
        )

        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 0),
            end_utc7=datetime(2026, 8, 24, 16, 10),
            output_path=tmp_path / "duplicate.md",
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        assert len(result.signals) == 1
        assert result.counts.duplicate_suppressed == 1
        assert result.counts.m5_cooldown_suppressed == 0

    def test_invalid_csv_schema_fails_before_writing_output(self, tmp_path):
        bad_path = tmp_path / "bad.csv"
        pd.DataFrame({"timestamp": ["2026-08-24 16:00:00"], "close": [100.0]}).to_csv(
            bad_path, index=False
        )
        valid = tmp_path / "valid.csv"
        _write_ohlcv_csv(valid, [BASE], [100.0], timedelta(minutes=5))

        with pytest.raises(SignalReplayInputError, match="missing columns"):
            run_btc_alert_replay(
                bad_path,
                valid,
                valid,
                output_path=tmp_path / "should-not-exist.md",
            )

        assert not (tmp_path / "should-not-exist.md").exists()


def test_render_replay_markdown_is_repeatable_for_fixed_generation_time(tmp_path):
    m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
    result = run_btc_alert_replay(
        m5_path,
        m15_path,
        h4_path,
        start_utc7=datetime(2026, 8, 24, 16, 40),
        end_utc7=datetime(2026, 8, 24, 17, 10),
        output_path=tmp_path / "replay.md",
        generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
    )
    generated_at = datetime(2026, 8, 28, 18, 30, tzinfo=UTC)

    assert render_replay_markdown(result, generated_at=generated_at) == render_replay_markdown(
        result, generated_at=generated_at
    )
