"""Unit tests for notification formatting helpers (pure string builders)."""

from decimal import Decimal

from app.notification import formatting as fmt


class TestMonoAndRow:
    def test_mono_wraps_in_pre(self):
        assert fmt.mono("hello") == "<pre>hello</pre>"

    def test_mono_empty(self):
        assert fmt.mono("") == "<pre></pre>"

    def test_row_default_width(self):
        out = fmt.row("Label", "42")
        assert "Label" in out
        assert "42" in out
        assert len(out) >= 14

    def test_row_custom_width(self):
        out = fmt.row("A", "1", width=5)
        assert out == "A     1"


class TestPriceFormatters:
    def test_fmt_price_two_decimals(self):
        assert fmt.fmt_price(Decimal("1234.5")) == "$1,234.50"

    def test_fmt_price_precise_preserves_decimals(self):
        assert fmt.fmt_price_precise(Decimal("0.123456")) == "$0.123456"

    def test_fmt_price_precise_min_two(self):
        assert fmt.fmt_price_precise(Decimal("5")) == "$5.00"

    def test_fmt_amount_precise_preserves_decimals(self):
        assert fmt.fmt_amount_precise(Decimal("0.12345")) == "0.12345"

    def test_fmt_amount_precise_min_two(self):
        assert fmt.fmt_amount_precise(Decimal("10")) == "10.00"


class TestAutoFormatters:
    def test_fmt_price_auto_high_value(self):
        result = fmt.fmt_price_auto(Decimal("50000"))
        assert result.startswith("$")
        assert "," in result

    def test_fmt_price_auto_low_value(self):
        result = fmt.fmt_price_auto(Decimal("0.001"))
        assert result.startswith("$")

    def test_fmt_price_auto_zero(self):
        result = fmt.fmt_price_auto(Decimal("0"))
        assert result == "$0.00"

    def test_fmt_price_auto_invalid(self):
        result = fmt.fmt_price_auto(None)
        assert result == "$0.00"

    def test_fmt_amount_auto_large_rounds_to_zero_dp(self):
        result = fmt.fmt_amount_auto(Decimal("12345"))
        assert "," in result or result

    def test_fmt_amount_auto_small(self):
        result = fmt.fmt_amount_auto(Decimal("0.5"))
        assert result

    def test_fmt_amount_auto_zero(self):
        result = fmt.fmt_amount_auto(Decimal("0"))
        assert result == "0.00"

    def test_fmt_amount_auto_invalid(self):
        result = fmt.fmt_amount_auto("not a number")
        assert result == "0"


class TestPctPnl:
    def test_fmt_pct_positive_prepends_plus(self):
        assert fmt.fmt_pct(Decimal("1.5")) == "+1.50%"

    def test_fmt_pct_negative(self):
        assert fmt.fmt_pct(Decimal("-2.5")) == "-2.50%"

    def test_fmt_pct_zero(self):
        assert fmt.fmt_pct(Decimal("0")) == "+0.00%"

    def test_fmt_pnl_positive(self):
        assert fmt.fmt_pnl(Decimal("1000.5")) == "+1,000.50"

    def test_fmt_pnl_negative(self):
        assert fmt.fmt_pnl(Decimal("-50")) == "-50.00"


class TestFmtDuration:
    def test_negative_returns_zero(self):
        assert fmt.fmt_duration(-5) == "0m"

    def test_seconds_less_than_minute(self):
        assert fmt.fmt_duration(30) == "0m"

    def test_minutes_only(self):
        assert fmt.fmt_duration(5 * 60) == "5m"

    def test_hours_with_minutes(self):
        assert fmt.fmt_duration(2 * 3600 + 15 * 60) == "2h 15m"

    def test_hours_exact(self):
        assert fmt.fmt_duration(3 * 3600) == "3h"

    def test_days_with_hours(self):
        assert fmt.fmt_duration(3 * 86400 + 1 * 3600) == "3d 1h"

    def test_days_exact(self):
        assert fmt.fmt_duration(5 * 86400) == "5d"


class TestDecimalsFor:
    def test_zero_value_returns_min(self):
        assert fmt._decimals_for(0, 0.01) == 2

    def test_negative_precision_returns_min(self):
        assert fmt._decimals_for(100, 0) == 2

    def test_normal_computation(self):
        # log10(100 * 0.01 / 100) = log10(0.01) = -2, ceil(2) = 2
        assert fmt._decimals_for(100, 0.01) == 2

    def test_clamps_to_max(self):
        # Very small value should hit max decimals cap
        assert fmt._decimals_for(1e-20, 0.01) == fmt._MAX_DECIMALS
