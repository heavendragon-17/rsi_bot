"""Offline checks for immutable, checked BTC research data acquisition."""

import csv
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

from research import btc_four_year_data as data


def _row(stamp, close=110.0):
    return stamp, (100.0, 120.0, 90.0, close, 42.0)


def _archive(rows, name="BTCUSDT-5m-2022-08.zip", *, header=True):
    handle = io.StringIO(newline="")
    writer = csv.writer(handle)
    if header:
        writer.writerow(["open_time", *data.FIELDS[1:], "close_time", "quote_volume"])
    writer.writerows((int((stamp - data.EPOCH).total_seconds() * 1000), *values, 0, 0)
                    for stamp, values in rows)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name.removesuffix(".zip") + ".csv", handle.getvalue())
    payload = buffer.getvalue()
    return payload, f"{data.sha256(payload)}  {name}\n".encode()


@pytest.mark.parametrize("header", [True, False])
def test_archive_header_and_millisecond_open_timestamp(header):
    stamp = datetime(2022, 8, 1, 0, 5, tzinfo=UTC)
    payload, checksum = _archive([_row(stamp)], header=header)
    assert data.parse_archive(payload, checksum, "BTCUSDT-5m-2022-08.zip") == [_row(stamp)]


def test_checksum_rejects_tampering_and_wrong_filename():
    payload, checksum = _archive([_row(datetime(2022, 8, 1, tzinfo=UTC))])
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        data.parse_archive(payload + b"corruption", checksum, "BTCUSDT-5m-2022-08.zip")
    with pytest.raises(ValueError, match="Invalid checksum entry"):
        data.verify_checksum(payload, checksum, "BTCUSDT-15m-2022-08.zip")


def test_archive_does_not_accept_unexpected_member_paths():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../outside.csv", "untrusted")
    payload = buffer.getvalue()
    name = "BTCUSDT-5m-2022-08.zip"
    checksum = f"{data.sha256(payload)}  {name}".encode()
    with pytest.raises(ValueError, match="Unexpected ZIP members"):
        data.parse_archive(payload, checksum, name)


def test_native_csv_normalizes_utc_plus_seven_and_preserves_aware_utc():
    prefix = b"timestamp,open,high,low,close,volume\n"
    naive = data.parse_csv(prefix + b"2022-08-01 07:00:00,100,120,90,110,42\n")
    aware = data.parse_csv(prefix + b"2022-08-01T00:00:00Z,100,120,90,110,42\n")
    assert naive == aware == [_row(datetime(2022, 8, 1, tzinfo=UTC))]


def test_merge_requires_matching_overlap_and_preserves_later_native_rows():
    start = datetime(2022, 8, 1, tzinfo=UTC)
    prefix = [_row(start), _row(start + timedelta(minutes=5))]
    existing = [_row(start + timedelta(minutes=5), 110.0 + 1e-12), _row(start + timedelta(minutes=10))]
    merged, overlaps = data.merge_overlap(prefix, existing)
    assert overlaps == 1
    assert merged == [prefix[0], *existing]
    with pytest.raises(ValueError, match="Conflicting archive/native"):
        data.merge_overlap(prefix, [_row(start + timedelta(minutes=5), 110.1)])
    with pytest.raises(ValueError, match="No archive/native overlap"):
        data.merge_overlap(prefix, [_row(start + timedelta(minutes=15))])
    with pytest.raises(ValueError, match="Duplicate timestamp"):
        data.merge_overlap(prefix + [prefix[-1]], existing)


@pytest.mark.parametrize("timeframe", list(data.TIMEFRAMES))
def test_exact_exchange_alignment_and_cadence(timeframe):
    start = datetime(2022, 8, 1, tzinfo=UTC)
    step = timedelta(minutes=data.TIMEFRAMES[timeframe])
    rows = [_row(start), _row(start + step)]
    data.validate_rows(rows, timeframe, start=start, end=start + 2 * step)
    with pytest.raises(ValueError, match="Misaligned"):
        data.validate_rows([_row(start + timedelta(seconds=1))], timeframe)
    with pytest.raises(ValueError, match="Duplicate, unordered, or missing"):
        data.validate_rows([rows[0], _row(start + 2 * step)], timeframe)
    with pytest.raises(ValueError, match="Duplicate, unordered, or missing"):
        data.validate_rows([rows[0], rows[0]], timeframe)
    with pytest.raises(ValueError, match="Missing requested.*interval"):
        data.validate_rows(rows, timeframe, end=start + 3 * step)
    with pytest.raises(ValueError, match="Missing requested.*start"):
        data.validate_rows(rows, timeframe, start=start - step)


@pytest.mark.parametrize("values", [
    (100, 120, 90, float("nan"), 42), (100, 120, 90, 110, float("inf")),
    (100, 120, 0, 110, 42), (100, 105, 90, 110, 42), (100, 120, 90, 110, -1),
])
def test_rejects_bad_ohlcv(values):
    with pytest.raises(ValueError, match="Non-finite|Invalid OHLC"):
        data.validate_rows([(datetime(2022, 8, 1, tzinfo=UTC), values)], "5m")


@pytest.fixture
def local_acquisition(tmp_path, monkeypatch):
    month = datetime(2022, 8, 1, tzinfo=UTC)
    for name, value in {"WARMUP_START": month, "SIGNAL_START": month + timedelta(days=1),
                        "SIGNAL_END": month + timedelta(days=2),
                        "OUTCOME_END": month + timedelta(days=2, hours=4),
                        "LAST_PREFIX_MONTH": month}.items():
        monkeypatch.setattr(data, name, value)
    source, output, cache = (tmp_path / name for name in ("source", "output", "cache"))
    source.mkdir()
    original_bytes = {}
    archive_dir = tmp_path / "fixtures"
    archive_dir.mkdir()
    records = {}
    for timeframe, minutes in data.TIMEFRAMES.items():
        step = timedelta(minutes=minutes)
        native = [_row(month + timedelta(days=30) + index * step) for index in range(2)]
        path = source / f"BTCUSDT_{timeframe}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(data.FIELDS)
            writer.writerows((data.utc_iso(stamp), *values) for stamp, values in native)
        original_bytes[timeframe] = path.read_bytes()
        rows = [_row(month + index * step) for index in range(31 * 1440 // minutes)]
        name = f"BTCUSDT-{timeframe}-2022-08.zip"
        payload, checksum = _archive(rows, name)
        archive_path, checksum_path = archive_dir / name, archive_dir / (name + ".CHECKSUM")
        archive_path.write_bytes(payload)
        checksum_path.write_bytes(checksum)
        records[timeframe] = {"timeframe": timeframe, "month": "2022-08", "path": str(archive_path),
                              "checksum_path": str(checksum_path), "sha256": data.sha256(payload)}
    monkeypatch.setattr(data, "cache_archive", lambda job, *_: records[job[0]])
    return source, output, cache, original_bytes


def test_offline_acquisition_publishes_checked_manifest_without_editing_native(local_acquisition):
    from app.backtest.signal_replay_data import load_ohlcv_csv

    source, output, cache, original_bytes = local_acquisition
    manifest = data.acquire(source, output, cache)
    assert manifest["status"] == "COMPLETE"
    assert json.loads((output / "acquisition_manifest.json").read_text()) == manifest
    for timeframe, payload in original_bytes.items():
        assert (source / f"BTCUSDT_{timeframe}.csv").read_bytes() == payload
        snapshot = cache / "native_sources" / data.sha256(payload) / f"BTCUSDT_{timeframe}.csv"
        assert snapshot.read_bytes() == payload
        path = output / f"BTCUSDT_{timeframe}.csv"
        assert data.sha256(path.read_bytes()) == manifest["outputs"][timeframe]["sha256"]
        frame = load_ohlcv_csv(path, timeframe)
        assert len(frame) == manifest["outputs"][timeframe]["row_count"]
        assert frame.index[0] == data.WARMUP_START
        assert manifest["outputs"][timeframe]["verified_overlap_rows"] == 2
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        data.acquire(source, output, cache)


def test_partial_archive_failure_never_publishes_dataset(local_acquisition, monkeypatch):
    source, output, cache, original_bytes = local_acquisition

    def fail_download(*_):
        raise OSError("Fixture archive unavailable")

    monkeypatch.setattr(data, "cache_archive", fail_download)
    with pytest.raises(OSError, match="Fixture archive unavailable"):
        data.acquire(source, output, cache)
    assert not output.exists()
    assert all((source / f"BTCUSDT_{tf}.csv").read_bytes() == payload for tf, payload in original_bytes.items())


def test_plan_is_read_only_and_does_not_download(local_acquisition, monkeypatch):
    source, output, cache, _ = local_acquisition
    monkeypatch.setattr(data, "cache_archive", lambda *_: pytest.fail("Unexpected download"))
    manifest = data.acquire(source, output, cache, plan_only=True)
    assert manifest["status"] == "PLANNED"
    assert manifest["months_by_timeframe"] == {timeframe: ["2022-08"] for timeframe in data.TIMEFRAMES}
    assert not cache.exists()
    assert not output.exists()


def test_protected_destination_is_rejected_before_source_reads(tmp_path):
    with pytest.raises(ValueError, match="separate from canonical/native"):
        data.acquire(tmp_path / "source", tmp_path / "source" / "output", tmp_path / "cache")
