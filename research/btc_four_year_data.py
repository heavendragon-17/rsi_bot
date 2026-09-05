"""Acquire an immutable four-year BTC research dataset from checked public archives."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import structlog

ROOT = Path(__file__).resolve().parents[1]
TIMEFRAMES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}
FIELDS = ("timestamp", "open", "high", "low", "close", "volume")
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
WARMUP_START = datetime(2022, 5, 1, tzinfo=UTC)
SIGNAL_START = datetime(2022, 8, 28, tzinfo=UTC)
SIGNAL_END = datetime(2026, 8, 28, tzinfo=UTC)
OUTCOME_END = SIGNAL_END + timedelta(hours=4)
LAST_PREFIX_MONTH = datetime(2024, 8, 1, tzinfo=UTC)
BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT"
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_CSV_BYTES = 64 * 1024 * 1024
REL_TOL, ABS_TOL = 1e-12, 1e-10
Row = tuple[datetime, tuple[float, ...]]
log = structlog.get_logger()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def next_month(value: datetime) -> datetime:
    return value.replace(year=value.year + (value.month == 12), month=value.month % 12 + 1, day=1)


def verify_checksum(payload: bytes, checksum: bytes, filename: str) -> str:
    """Bind a SHA256 checksum to its exact archive filename before parsing ZIP bytes."""
    parts = checksum.decode("ascii").strip().split()
    if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]) or parts[1].lstrip("*") != filename:
        raise ValueError(f"Invalid checksum entry for {filename}")
    digest = sha256(payload)
    if digest != parts[0].lower():
        raise ValueError(f"SHA256 mismatch for {filename}")
    return digest


def parse_csv(payload: bytes, *, archive: bool = False) -> list[Row]:
    """Parse native UTC+7 CSVs or Binance millisecond klines without implicit repair."""
    reader = csv.reader(io.StringIO(payload.decode("utf-8-sig"), newline=""))
    rows: list[Row] = []
    for number, fields in enumerate(reader, 1):
        if number == 1:
            header = tuple(value.strip().lower().replace(" ", "_") for value in fields[:6])
            expected = ("open_time", *FIELDS[1:]) if archive else FIELDS
            if header == expected:
                continue
            if not archive:
                raise ValueError("Native CSV must have timestamp,open,high,low,close,volume header")
        if len(fields) < 6 or (not archive and len(fields) != 6):
            raise ValueError(f"Invalid CSV row {number}: expected OHLCV columns")
        if archive:
            if not fields[0].isdecimal():
                raise ValueError(f"Archive timestamp must be integer milliseconds at row {number}")
            stamp = EPOCH + timedelta(milliseconds=int(fields[0]))
        else:
            stamp = datetime.fromisoformat(fields[0])
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone(timedelta(hours=7)))
            stamp = stamp.astimezone(UTC)
        rows.append((stamp, tuple(float(value) for value in fields[1:6])))
    if not rows:
        raise ValueError("CSV contains no candles")
    return rows


def parse_archive(payload: bytes, checksum: bytes, filename: str) -> list[Row]:
    verify_checksum(payload, checksum, filename)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != filename.removesuffix(".zip") + ".csv":
            raise ValueError(f"Unexpected ZIP members in {filename}")
        if members[0].file_size > MAX_CSV_BYTES:
            raise ValueError(f"Uncompressed CSV exceeds limit: {filename}")
        # Read in memory; never extract archive-controlled paths into the filesystem.
        return parse_csv(archive.read(members[0]), archive=True)


def validate_rows(rows: list[Row], timeframe: str, *, start: datetime | None = None,
                  end: datetime | None = None) -> None:
    """Require exact UTC exchange alignment and uninterrupted, strictly ordered OHLCV."""
    if not rows:
        raise ValueError(f"No {timeframe} candles")
    step = timedelta(minutes=TIMEFRAMES[timeframe])
    previous = None
    for stamp, values in rows:
        if stamp.tzinfo is None or (stamp - EPOCH) % step != timedelta(0):
            raise ValueError(f"Misaligned {timeframe} candle: {stamp}")
        if previous is not None and stamp - previous != step:
            raise ValueError(f"Duplicate, unordered, or missing {timeframe} candle after {previous}")
        if len(values) != 5 or not all(math.isfinite(value) for value in values):
            raise ValueError(f"Non-finite or invalid OHLCV at {stamp}")
        opening, high, low, close, volume = values
        if min(opening, high, low, close) <= 0 or volume < 0 or not low <= min(opening, close) <= max(opening, close) <= high:
            raise ValueError(f"Invalid OHLC relations, price, or volume at {stamp}")
        previous = stamp
    if start is not None and rows[0][0] != start:
        raise ValueError(f"Missing requested {timeframe} start: {start}")
    if end is not None and rows[-1][0] + step < end:
        raise ValueError(f"Missing requested {timeframe} interval through {end}")


def merge_overlap(prefix: list[Row], existing: list[Row]) -> tuple[list[Row], int]:
    """Coalesce verified cross-source overlap; reject duplicates within either source."""
    merged = dict(prefix)
    if len(merged) != len(prefix) or len(dict(existing)) != len(existing):
        raise ValueError("Duplicate timestamp within a source")
    overlaps = 0
    for stamp, values in existing:
        if stamp in merged:
            # float serialization differences only: well below BTC tick/volume units.
            if not all(math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)
                       for a, b in zip(merged[stamp], values, strict=True)):
                raise ValueError(f"Conflicting archive/native OHLCV overlap at {utc_iso(stamp)}")
            overlaps += 1
        merged[stamp] = values
    if not overlaps:
        raise ValueError("No archive/native overlap available to verify market identity")
    return sorted(merged.items()), overlaps


def fetch(url: str, *, timeout: float, retries: int, limit: int) -> bytes:
    for attempt in range(retries):
        try:
            deadline = time.monotonic() + timeout
            request = urllib.request.Request(url, headers={"User-Agent": "rsi-bot-btc-research/1"})
            with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed HTTPS source
                chunks, count = [], 0
                while chunk := response.read(64 * 1024):
                    count += len(chunk)
                    if count > limit or time.monotonic() > deadline:
                        raise ValueError(f"Download exceeds byte/time bound: {url}")
                    chunks.append(chunk)
                return b"".join(chunks)
        except (OSError, urllib.error.URLError, ValueError):
            if attempt + 1 == retries:
                raise
            time.sleep(min(2, attempt + 1))
    raise ValueError("At least one download attempt is required")


def cache_archive(job: tuple[str, datetime], cache: Path, timeout: float, retries: int) -> dict:
    timeframe, month = job
    filename = f"BTCUSDT-{timeframe}-{month:%Y-%m}.zip"
    url = f"{BASE_URL}/{timeframe}/{filename}"
    directory = cache / "archives" / timeframe
    directory.mkdir(parents=True, exist_ok=True)
    archive_path, checksum_path = directory / filename, directory / (filename + ".CHECKSUM")
    checksum = checksum_path.read_bytes() if checksum_path.exists() else fetch(
        url + ".CHECKSUM", timeout=timeout, retries=retries, limit=4096)
    payload = archive_path.read_bytes() if archive_path.exists() else fetch(
        url, timeout=timeout, retries=retries, limit=MAX_ARCHIVE_BYTES)
    digest = verify_checksum(payload, checksum, filename)
    for path, content in ((archive_path, payload), (checksum_path, checksum)):
        if not path.exists():
            partial = path.with_name(path.name + ".partial")
            partial.write_bytes(content)
            partial.replace(path)
    log.info("btc_archive_verified", timeframe=timeframe, month=f"{month:%Y-%m}")
    return {"timeframe": timeframe, "month": f"{month:%Y-%m}", "url": url,
            "checksum_url": url + ".CHECKSUM", "path": str(archive_path), "sha256": digest,
            "checksum_path": str(checksum_path), "checksum_sha256": sha256(checksum)}


def row_facts(rows: list[Row], timeframe: str) -> dict:
    return {"row_count": len(rows), "start_open_utc": utc_iso(rows[0][0]),
            "end_open_utc": utc_iso(rows[-1][0]),
            "end_close_utc": utc_iso(rows[-1][0] + timedelta(minutes=TIMEFRAMES[timeframe]))}


def acquire(source: Path, output: Path, cache: Path, *, workers: int = 4,
            timeout: float = 20, retries: int = 3, plan_only: bool = False) -> dict:
    source, output, cache = source.resolve(), output.resolve(), cache.resolve()
    if not 1 <= workers <= 4 or not 1 <= timeout <= 60 or not 1 <= retries <= 5:
        raise ValueError("Bounds: workers 1..4, timeout 1..60 seconds, retries 1..5")
    canonical = (ROOT / "app/backtest/data").resolve()
    if any(path.is_relative_to(protected) for path in (output, cache) for protected in (source, canonical)):
        raise ValueError("Output and cache must be separate from canonical/native source directories")
    if cache == output or cache.is_relative_to(output) or output.is_relative_to(cache):
        raise ValueError("Output and cache directories must be separate")
    if output.exists() and not plan_only:
        raise FileExistsError(f"Refusing to overwrite existing dataset: {output}")
    originals, jobs, local_sources = {}, [], {}
    for timeframe in TIMEFRAMES:
        path = source / f"BTCUSDT_{timeframe}.csv"
        payload = path.read_bytes()
        rows = parse_csv(payload)
        validate_rows(rows, timeframe, end=OUTCOME_END)
        originals[timeframe] = rows
        overlap_month = rows[0][0].replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if not WARMUP_START <= overlap_month <= LAST_PREFIX_MONTH:
            raise ValueError(f"Native {timeframe} start outside supported prefix range: {overlap_month}")
        month = WARMUP_START
        while month <= overlap_month:
            jobs.append((timeframe, month))
            month = next_month(month)
        digest = sha256(payload)
        snapshot = cache / "native_sources" / digest / path.name
        local_sources[timeframe] = {"path": str(path), "sha256": digest, "snapshot_path": str(snapshot),
                                   **row_facts(rows, timeframe)}
        if not plan_only:
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            if snapshot.exists() and sha256(snapshot.read_bytes()) != digest:
                raise ValueError(f"Corrupt native source snapshot: {snapshot}")
            if not snapshot.exists():
                snapshot.write_bytes(payload)
    manifest = {"status": "PLANNED", "schema": "btc-four-year-data-v1", "symbol": "BTCUSDT",
                "venue": "Binance USD-M Futures", "warmup_start_utc": utc_iso(WARMUP_START),
                "signal_start_inclusive_utc": utc_iso(SIGNAL_START),
                "signal_end_exclusive_utc": utc_iso(SIGNAL_END),
                "required_outcome_end_close_utc": utc_iso(OUTCOME_END),
                "post_signal_end_usage": "outcome labels only; never new signal candidates",
                "overlap_tolerance": {"relative": REL_TOL, "absolute": ABS_TOL},
                "local_sources": local_sources, "archive_count": len(jobs)}
    if plan_only:
        manifest["months_by_timeframe"] = {tf: [f"{month:%Y-%m}" for kind, month in jobs if kind == tf]
                                            for tf in TIMEFRAMES}
        return manifest
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(cache_archive, job, cache, timeout, retries) for job in jobs]
        archives = [future.result() for future in futures]
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=output.name + ".partial-", dir=output.parent))
    outputs = {}
    for timeframe in TIMEFRAMES:
        prefix = []
        for archive in (item for item in archives if item["timeframe"] == timeframe):
            path = Path(archive["path"])
            rows = parse_archive(path.read_bytes(), Path(archive["checksum_path"]).read_bytes(), path.name)
            month = datetime.strptime(archive["month"], "%Y-%m").replace(tzinfo=UTC)
            validate_rows(rows, timeframe, start=month, end=next_month(month))
            if rows[-1][0] >= next_month(month):
                raise ValueError(f"Archive contains candles outside its month: {path.name}")
            archive.update(row_facts(rows, timeframe))
            prefix.extend(rows)
        validate_rows(prefix, timeframe, start=WARMUP_START)
        combined, overlap_count = merge_overlap(prefix, originals[timeframe])
        validate_rows(combined, timeframe, start=WARMUP_START, end=OUTCOME_END)
        path = staging / f"BTCUSDT_{timeframe}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(FIELDS)
            writer.writerows((utc_iso(stamp), *values) for stamp, values in combined)
        outputs[timeframe] = {"filename": path.name, "sha256": sha256(path.read_bytes()),
                              "verified_overlap_rows": overlap_count, **row_facts(combined, timeframe)}
    manifest.update(status="COMPLETE", acquired_at_utc=utc_iso(datetime.now(UTC)),
                    archives=archives, outputs=outputs)
    (staging / "acquisition_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    staging.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "app/backtest/data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/data/btc_four_year_20220828_20260828")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "research/data/btc_four_year_archive_cache")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--plan", action="store_true", help="Validate native inputs and show monthly plan without writing or networking")
    args = parser.parse_args()
    result = acquire(args.source_dir, args.output_dir, args.cache_dir, workers=args.workers,
                     timeout=args.timeout, retries=args.retries, plan_only=args.plan)
    log.info("btc_four_year_acquisition", manifest=result)


if __name__ == "__main__":
    main()
