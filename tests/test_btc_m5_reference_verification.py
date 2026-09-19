"""Fail-closed numerical reproduction checks for the frozen M5 study."""
import pytest


def test_compare_reference_fields_detects_numerical_drift_and_missing_fields():
    from research.btc_m5_reference_verification import compare_reference_fields

    assert compare_reference_fields({"pnl": 1.0, "scope": "account"}, {"pnl": 1.0, "scope": "account", "new": 3}) == 2
    with pytest.raises(ValueError, match="pnl"):
        compare_reference_fields({"pnl": 1.0}, {"pnl": 2.0})
    with pytest.raises(ValueError, match="pnl"):
        compare_reference_fields({"pnl": 1.0}, {})
    with pytest.raises(ValueError, match="pnl"):
        compare_reference_fields({"pnl": None}, {"pnl": 0.0})


def test_repeat_requires_exact_bytes(tmp_path):
    from research.btc_m5_reference_verification import verify_repeat

    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    for path in (a, b):
        (path / "protocol.json").write_text('{}\n', encoding="utf-8")
        (path / "summary.json").write_text('{}\n', encoding="utf-8")
        (path / "equity_daily.csv").write_text('timestamp,equity\n', encoding="utf-8")
        (path / "full").mkdir()
        for name in ("actions.csv", "trades.csv", "equity_curve.csv", "signals.csv"):
            (path / "full" / name).write_text('value\n', encoding="utf-8")
    assert len(verify_repeat(a, b)) == 7
    (b / "full" / "trades.csv").write_text('different\n', encoding="utf-8")
    with pytest.raises(ValueError, match="trades.csv"):
        verify_repeat(a, b)
