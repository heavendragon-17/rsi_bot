"""Versioned data contract and validation for Signal Review ZIP bundles."""

from __future__ import annotations

import hashlib
import json
import math
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

BUNDLE_FORMAT = "rsi-bot-signal-review"
BUNDLE_VERSION = 1
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_REVIEW_BYTES = 128 * 1024 * 1024

SOURCE_MEMBERS: dict[str, str] = {
    "5m": "sources/BTCUSDT_5m.csv",
    "15m": "sources/BTCUSDT_15m.csv",
    "1h": "sources/BTCUSDT_1h.csv",
    "4h": "sources/BTCUSDT_4h.csv",
}
SMALL_MEMBERS = {"review.json", "README.txt"}
EXPECTED_MEMBERS = {"manifest.json", *SMALL_MEMBERS, *SOURCE_MEMBERS.values()}


class SignalReviewBundleError(ValueError):
    """Raised when a bundle cannot be safely exported or imported."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BundleRun(_StrictModel):
    status: Literal["completed"]
    strategy_name: str
    definition_version: str
    git_hash: str | None
    symbol: str
    requested_start_at: datetime | None
    requested_end_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    source_metadata: dict[str, dict[str, Any]]
    counters: dict[str, Any]
    error_message: str | None


class BundleReview(_StrictModel):
    quality: Literal["UNREVIEWED", "GOOD", "BAD", "UNCERTAIN"]
    human_outcome: Literal["UNSET", "WIN", "LOSS", "SKIP"]
    note: str | None
    reviewed_at: datetime | None
    updated_at: datetime | None
    future_unlocked_at: datetime | None
    take_profit_price: str | None
    stop_loss_price: str | None
    exit_reason: (
        Literal[
            "TAKE_PROFIT",
            "STOP_LOSS",
            "BOTH_SAME_CANDLE",
            "OPEN",
            "NO_DATA",
        ]
        | None
    )
    exit_at: datetime | None
    duration_minutes: int | None
    evaluation_warning: str | None
    evaluated_at: datetime | None


class BundleMetric(_StrictModel):
    horizon_minutes: int = Field(gt=0)
    price_at_observation: str | None
    return_pct: float | None
    mfe_pct: float | None
    mae_pct: float | None
    observed_at: datetime | None
    complete: bool
    warning: str | None


class BundleSignal(_StrictModel):
    event_id: str = Field(min_length=1)
    sequence: int = Field(gt=0)
    timeframe: Literal["5m", "15m"]
    definition_version: str
    trigger_open_at: datetime
    trigger_close_at: datetime
    trigger_close_price: str
    trigger_price_ema21: str
    rsi21: float
    rsi_ema9: float
    rsi_wma45: float
    rsi_spread: float
    previous_rsi_ema9: float | None
    previous_rsi_wma45: float | None
    h4_close_price: str
    h4_price_ema21: str
    h4_close_at: datetime
    decision_reason: str
    telegram_card: str
    snapshot: dict[str, Any]
    review: BundleReview
    forward_metrics: list[BundleMetric]


class BundlePayload(_StrictModel):
    schema_version: Literal[1]
    run: BundleRun
    signals: list[BundleSignal]


class BundleFile(_StrictModel):
    sha256: str
    size: int = Field(ge=0)


class BundleCounts(_StrictModel):
    signal_count: int = Field(ge=0)
    reviewed_count: int = Field(ge=0)
    m5_count: int = Field(ge=0)
    m15_count: int = Field(ge=0)


class BundleManifest(_StrictModel):
    format: Literal["rsi-bot-signal-review"]
    format_version: Literal[1]
    bundle_id: str
    exported_at: datetime
    source_run_id: int = Field(gt=0)
    counts: BundleCounts
    files: dict[str, BundleFile]
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class BundleArtifact:
    path: Path
    filename: str
    bundle_id: str


@dataclass(frozen=True, slots=True)
class BundleImportResult:
    run_id: int
    bundle_id: str
    duplicate: bool
    signal_count: int
    reviewed_count: int
    source_run_id: int


@dataclass(frozen=True, slots=True)
class ValidatedBundle:
    manifest: BundleManifest
    payload: BundlePayload
    raw_payload: dict[str, Any]
    manifest_bytes: bytes
    review_bytes: bytes
    readme_bytes: bytes


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


def utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.replace(tzinfo=None)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_identity(payload: dict[str, Any], source_hashes: dict[str, str]) -> dict[str, Any]:
    run = payload["run"]
    return {
        "format": BUNDLE_FORMAT,
        "format_version": BUNDLE_VERSION,
        "run": {
            "strategy_name": run["strategy_name"],
            "definition_version": run["definition_version"],
            "git_hash": run["git_hash"],
            "symbol": run["symbol"],
            "requested_start_at": run["requested_start_at"],
            "requested_end_at": run["requested_end_at"],
        },
        "signals": payload["signals"],
        "source_sha256": source_hashes,
    }


def _strict_json_loads(raw: bytes, label: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON value {value}")

    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SignalReviewBundleError(f"{label} is not valid UTF-8 JSON: {exc}") from None
    if not isinstance(value, dict):
        raise SignalReviewBundleError(f"{label} must contain one JSON object")
    pending: list[Any] = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, float) and not math.isfinite(item):
            raise SignalReviewBundleError(f"{label} contains a non-finite number")
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return value


def _hash_archive_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info, "r") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_payload(payload: BundlePayload) -> None:
    if payload.run.strategy_name != "btc_rsi_cross_alert" or payload.run.symbol != "BTC/USDT":
        raise SignalReviewBundleError("Bundle is not a BTC RSI Signal Review dataset")
    if set(payload.run.source_metadata) != set(SOURCE_MEMBERS):
        raise SignalReviewBundleError("Bundle must describe exactly the M5, M15, H1, and H4 sources")
    event_ids: set[str] = set()
    sequences: set[int] = set()
    for signal in payload.signals:
        if signal.event_id in event_ids or signal.sequence in sequences:
            raise SignalReviewBundleError("Bundle contains duplicate signal identity or sequence values")
        event_ids.add(signal.event_id)
        sequences.add(signal.sequence)
        if signal.definition_version != payload.run.definition_version:
            raise SignalReviewBundleError("Signal and run definition versions do not match")
        numeric_values = (
            signal.rsi21,
            signal.rsi_ema9,
            signal.rsi_wma45,
            signal.rsi_spread,
            signal.previous_rsi_ema9,
            signal.previous_rsi_wma45,
        )
        if any(value is not None and not math.isfinite(value) for value in numeric_values):
            raise SignalReviewBundleError(f"Signal {signal.event_id} contains a non-finite value")
        review = signal.review
        if review.quality == "UNREVIEWED" and review.human_outcome != "UNSET":
            raise SignalReviewBundleError("A human outcome cannot exist before a quality review")
        if (review.take_profit_price is None) != (review.stop_loss_price is None):
            raise SignalReviewBundleError("Take-profit and stop-loss must be present together")
        horizons = [metric.horizon_minutes for metric in signal.forward_metrics]
        if len(horizons) != len(set(horizons)):
            raise SignalReviewBundleError(f"Signal {signal.event_id} contains duplicate forward horizons")


def validate_archive(path: Path) -> ValidatedBundle:
    """Validate archive inventory, sizes, hashes, schema, semantics, and identity."""

    if not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise SignalReviewBundleError("Bundle is missing or exceeds the 1 GiB upload limit")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != EXPECTED_MEMBERS:
                raise SignalReviewBundleError("Bundle contains missing, duplicate, or unexpected files")
            infos = {info.filename: info for info in archive.infolist()}
            if sum(info.file_size for info in infos.values()) > MAX_UNCOMPRESSED_BYTES:
                raise SignalReviewBundleError("Bundle expands beyond the 2 GiB safety limit")
            for info in infos.values():
                if info.flag_bits & 0x1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise SignalReviewBundleError("Bundle uses an unsupported ZIP feature")
            if infos["manifest.json"].file_size > 1024 * 1024:
                raise SignalReviewBundleError("Bundle manifest is unexpectedly large")
            if infos["review.json"].file_size > MAX_REVIEW_BYTES:
                raise SignalReviewBundleError("Bundle review dataset is unexpectedly large")
            manifest_bytes = archive.read("manifest.json")
            manifest_data = _strict_json_loads(manifest_bytes, "manifest.json")
            try:
                manifest = BundleManifest.model_validate(manifest_data)
            except ValidationError as exc:
                raise SignalReviewBundleError(f"Bundle manifest is invalid: {exc}") from None
            if len(manifest.bundle_id) != 64 or any(char not in "0123456789abcdef" for char in manifest.bundle_id):
                raise SignalReviewBundleError("Bundle ID is invalid")
            if set(manifest.files) != EXPECTED_MEMBERS - {"manifest.json"}:
                raise SignalReviewBundleError("Bundle manifest file inventory is incomplete")
            for name, record in manifest.files.items():
                info = infos[name]
                if record.size != info.file_size:
                    raise SignalReviewBundleError(f"Bundle size check failed for {name}")
                if len(record.sha256) != 64 or _hash_archive_member(archive, info) != record.sha256:
                    raise SignalReviewBundleError(f"Bundle hash check failed for {name}")
            review_bytes = archive.read("review.json")
            readme_bytes = archive.read("README.txt")
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise SignalReviewBundleError(f"Bundle is not a readable ZIP archive: {exc}") from None

    raw_payload = _strict_json_loads(review_bytes, "review.json")
    try:
        payload = BundlePayload.model_validate(raw_payload)
    except ValidationError as exc:
        raise SignalReviewBundleError(f"Bundle review dataset is invalid: {exc}") from None
    _validate_payload(payload)
    source_hashes = {timeframe: manifest.files[member].sha256 for timeframe, member in SOURCE_MEMBERS.items()}
    expected_id = sha256_bytes(canonical_json_bytes(content_identity(raw_payload, source_hashes)))
    if manifest.bundle_id != expected_id:
        raise SignalReviewBundleError("Bundle identity does not match its review and source content")
    counts = manifest.counts
    if (
        counts.signal_count != len(payload.signals)
        or counts.reviewed_count != sum(signal.review.quality != "UNREVIEWED" for signal in payload.signals)
        or counts.m5_count != sum(signal.timeframe == "5m" for signal in payload.signals)
        or counts.m15_count != sum(signal.timeframe == "15m" for signal in payload.signals)
    ):
        raise SignalReviewBundleError("Bundle manifest counts do not match its review dataset")
    return ValidatedBundle(
        manifest=manifest,
        payload=payload,
        raw_payload=raw_payload,
        manifest_bytes=manifest_bytes,
        review_bytes=review_bytes,
        readme_bytes=readme_bytes,
    )
