"""Portable, hash-verified handoff bundles for BTC Signal Review runs."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.backtest.signal_replay_analysis import source_metadata
from app.backtest.signal_replay_bundle_format import (
    BUNDLE_FORMAT,
    BUNDLE_VERSION,
    SOURCE_MEMBERS,
    BundleArtifact,
    BundleImportResult,
    SignalReviewBundleError,
)
from app.backtest.signal_replay_bundle_format import (
    BundleSignal as _BundleSignal,
)
from app.backtest.signal_replay_bundle_format import (
    ValidatedBundle as _ValidatedBundle,
)
from app.backtest.signal_replay_bundle_format import (
    canonical_json_bytes as _json_bytes,
)
from app.backtest.signal_replay_bundle_format import (
    content_identity as _content_identity,
)
from app.backtest.signal_replay_bundle_format import (
    iso_utc as _iso,
)
from app.backtest.signal_replay_bundle_format import (
    sha256_bytes as _sha256_bytes,
)
from app.backtest.signal_replay_bundle_format import (
    sha256_file as _sha256_file,
)
from app.backtest.signal_replay_bundle_format import (
    utc_naive as _utc_naive,
)
from app.backtest.signal_replay_bundle_format import (
    validate_archive as _validate_archive,
)
from app.backtest.signal_replay_data import load_ohlcv_csv
from app.repository.backtest.database import DB_DIR
from app.repository.backtest.models import (
    SignalForwardMetric,
    SignalReplayRun,
    SignalReplaySignal,
    SignalReview,
)

IMPORT_ROOT = DB_DIR / "signal_review_imports"
CANONICAL_SOURCE_ROOT = Path(__file__).resolve().parent / "data"


def _serialize_review(review: SignalReview) -> dict[str, Any]:
    return {
        "quality": review.quality,
        "human_outcome": review.human_outcome,
        "note": review.note,
        "reviewed_at": _iso(review.reviewed_at),
        "updated_at": _iso(review.updated_at),
        "future_unlocked_at": _iso(review.future_unlocked_at),
        "take_profit_price": review.take_profit_price,
        "stop_loss_price": review.stop_loss_price,
        "exit_reason": review.exit_reason,
        "exit_at": _iso(review.exit_at),
        "duration_minutes": review.duration_minutes,
        "evaluation_warning": review.evaluation_warning,
        "evaluated_at": _iso(review.evaluated_at),
    }


def _serialize_signal(signal: SignalReplaySignal) -> dict[str, Any]:
    if signal.review is None:
        raise SignalReviewBundleError(f"Signal {signal.event_id} has no review row")
    return {
        "event_id": signal.event_id,
        "sequence": signal.sequence,
        "timeframe": signal.timeframe,
        "definition_version": signal.definition_version,
        "trigger_open_at": _iso(signal.trigger_open_at),
        "trigger_close_at": _iso(signal.trigger_close_at),
        "trigger_close_price": signal.trigger_close_price,
        "trigger_price_ema21": signal.trigger_price_ema21,
        "rsi21": signal.rsi21,
        "rsi_ema9": signal.rsi_ema9,
        "rsi_wma45": signal.rsi_wma45,
        "rsi_spread": signal.rsi_spread,
        "previous_rsi_ema9": signal.previous_rsi_ema9,
        "previous_rsi_wma45": signal.previous_rsi_wma45,
        "h4_close_price": signal.h4_close_price,
        "h4_price_ema21": signal.h4_price_ema21,
        "h4_close_at": _iso(signal.h4_close_at),
        "decision_reason": signal.decision_reason,
        "telegram_card": signal.telegram_card,
        "snapshot": signal.snapshot,
        "review": _serialize_review(signal.review),
        "forward_metrics": [
            {
                "horizon_minutes": metric.horizon_minutes,
                "price_at_observation": metric.price_at_observation,
                "return_pct": metric.return_pct,
                "mfe_pct": metric.mfe_pct,
                "mae_pct": metric.mae_pct,
                "observed_at": _iso(metric.observed_at),
                "complete": metric.complete,
                "warning": metric.warning,
            }
            for metric in sorted(signal.forward_metrics, key=lambda item: item.horizon_minutes)
        ],
    }


def _sanitize_source_metadata(metadata: dict[str, Any], filename: str, sha256: str) -> dict[str, Any]:
    sanitized = {key: value for key, value in metadata.items() if key != "path"}
    sanitized["filename"] = filename
    sanitized["sha256"] = sha256
    return sanitized


def _allowed_source(path: Path, allowed_roots: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(root.resolve()) for root in allowed_roots)


def _source_files_for_run(
    run: SignalReplayRun,
    allowed_roots: tuple[Path, ...],
) -> tuple[dict[str, Path], dict[str, dict[str, Any]], list[str]]:
    paths: dict[str, Path] = {}
    metadata_for_bundle: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    stored_sources = run.source_metadata or {}
    for timeframe, member in SOURCE_MEMBERS.items():
        stored = stored_sources.get(timeframe)
        if not isinstance(stored, dict):
            raise SignalReviewBundleError(f"Run {run.id} has no {timeframe} source metadata")
        raw_path = stored.get("path")
        path = Path(raw_path).resolve() if isinstance(raw_path, str) else None
        expected_name = Path(member).name
        if path is None or not path.is_file() or path.name != expected_name:
            raise SignalReviewBundleError(f"Run {run.id} {timeframe} source is unavailable")
        if not _allowed_source(path, allowed_roots):
            raise SignalReviewBundleError(f"Run {run.id} {timeframe} source is outside approved data folders")
        frame = load_ohlcv_csv(path, timeframe)
        current = source_metadata(path, frame, timeframe, include_sha256=True)
        for key in ("row_count", "available_start", "available_end"):
            if stored.get(key) is not None and stored.get(key) != current.get(key):
                raise SignalReviewBundleError(
                    f"Run {run.id} {timeframe} source {key.replace('_', ' ')} changed after replay"
                )
        stored_hash = stored.get("sha256")
        if stored_hash is not None and stored_hash != current["sha256"]:
            raise SignalReviewBundleError(f"Run {run.id} {timeframe} source hash changed after replay")
        if stored_hash is None:
            warnings.append(
                f"{timeframe} was created before replay-time hashing; the bundle binds the current validated source."
            )
        paths[timeframe] = path
        metadata_for_bundle[timeframe] = _sanitize_source_metadata(
            current,
            expected_name,
            current["sha256"],
        )
    return paths, metadata_for_bundle, warnings


def _bundle_filename(run: SignalReplayRun, bundle_id: str) -> str:
    start = (run.requested_start_at or run.created_at).strftime("%Y%m%d")
    end = (run.requested_end_at or run.completed_at or run.created_at).strftime("%Y%m%d")
    return f"BTC-signal-review-{start}-{end}-{bundle_id[:10]}.zip"


def create_signal_review_bundle(
    run_id: int,
    db: Session,
    *,
    output_dir: Path | None = None,
    allowed_source_roots: tuple[Path, ...] | None = None,
) -> BundleArtifact:
    """Create one portable archive without exposing unrelated database rows."""

    run = (
        db.query(SignalReplayRun)
        .options(
            selectinload(SignalReplayRun.signals).selectinload(SignalReplaySignal.review),
            selectinload(SignalReplayRun.signals).selectinload(SignalReplaySignal.forward_metrics),
        )
        .filter_by(id=run_id)
        .first()
    )
    if run is None:
        raise LookupError("Signal replay run not found")
    if run.status != "completed":
        raise SignalReviewBundleError("Only completed Signal Review runs can be exported")

    roots = allowed_source_roots or (CANONICAL_SOURCE_ROOT, IMPORT_ROOT)
    source_paths, source_facts, warnings = _source_files_for_run(run, roots)
    signals = [_serialize_signal(signal) for signal in sorted(run.signals, key=lambda item: item.sequence)]
    run_payload = {
        "status": "completed",
        "strategy_name": run.strategy_name,
        "definition_version": run.definition_version,
        "git_hash": run.git_hash,
        "symbol": run.symbol,
        "requested_start_at": _iso(run.requested_start_at),
        "requested_end_at": _iso(run.requested_end_at),
        "created_at": _iso(run.created_at),
        "started_at": _iso(run.started_at),
        "completed_at": _iso(run.completed_at),
        "source_metadata": source_facts,
        "counters": run.counters or {},
        "error_message": run.error_message,
    }
    payload = {"schema_version": BUNDLE_VERSION, "run": run_payload, "signals": signals}
    review_bytes = _json_bytes(payload)
    source_hashes = {timeframe: source_facts[timeframe]["sha256"] for timeframe in SOURCE_MEMBERS}
    bundle_id = _sha256_bytes(_json_bytes(_content_identity(payload, source_hashes)))
    reviewed_count = sum(signal["review"]["quality"] != "UNREVIEWED" for signal in signals)
    readme_bytes = (
        b"BTC Signal Review portable bundle\n\n"
        b"Send this ZIP file as-is. In RSI Bot, open Signal Review and click Import review bundle.\n"
        b"The importer validates every file and creates a separate local run; it does not overwrite existing reviews.\n"
    )
    files: dict[str, dict[str, Any]] = {
        "review.json": {"sha256": _sha256_bytes(review_bytes), "size": len(review_bytes)},
        "README.txt": {"sha256": _sha256_bytes(readme_bytes), "size": len(readme_bytes)},
    }
    for timeframe, member in SOURCE_MEMBERS.items():
        path = source_paths[timeframe]
        files[member] = {"sha256": source_hashes[timeframe], "size": path.stat().st_size}
    manifest = {
        "format": BUNDLE_FORMAT,
        "format_version": BUNDLE_VERSION,
        "bundle_id": bundle_id,
        "exported_at": datetime.now(UTC).isoformat(),
        "source_run_id": run.id,
        "counts": {
            "signal_count": len(signals),
            "reviewed_count": reviewed_count,
            "m5_count": sum(signal["timeframe"] == "5m" for signal in signals),
            "m15_count": sum(signal["timeframe"] == "15m" for signal in signals),
        },
        "files": files,
        "warnings": warnings,
    }

    destination = output_dir or Path(tempfile.gettempdir())
    destination.mkdir(parents=True, exist_ok=True)
    filename = _bundle_filename(run, bundle_id)
    fd, raw_path = tempfile.mkstemp(prefix="signal-review-", suffix=".zip", dir=destination)
    os.close(fd)
    archive_path = Path(raw_path)
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr("manifest.json", _json_bytes(manifest))
            archive.writestr("review.json", review_bytes)
            archive.writestr("README.txt", readme_bytes)
            for timeframe, member in SOURCE_MEMBERS.items():
                archive.write(source_paths[timeframe], member)
        _validate_archive(archive_path)
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise
    return BundleArtifact(path=archive_path, filename=filename, bundle_id=bundle_id)


def _find_existing_import(db: Session, bundle_id: str) -> SignalReplayRun | None:
    for run in db.query(SignalReplayRun).order_by(SignalReplayRun.id.desc()).all():
        marker = (run.source_metadata or {}).get("_review_bundle")
        if isinstance(marker, dict) and marker.get("bundle_id") == bundle_id:
            return run
    return None


def _extract_bundle_sources(
    archive_path: Path,
    validated: _ValidatedBundle,
    import_root: Path,
) -> tuple[Path, bool, dict[str, Any]]:
    import_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".signal-review-import-", dir=import_root))
    final_dir = import_root / validated.manifest.bundle_id
    created = False
    frames: dict[str, Any] = {}
    try:
        (staging / "manifest.json").write_bytes(validated.manifest_bytes)
        (staging / "review.json").write_bytes(validated.review_bytes)
        (staging / "README.txt").write_bytes(validated.readme_bytes)
        with zipfile.ZipFile(archive_path, "r") as archive:
            for timeframe, member in SOURCE_MEMBERS.items():
                target = staging / member
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.open(member, "r") as source, target.open("wb") as destination:
                    while chunk := source.read(1024 * 1024):
                        destination.write(chunk)
                        digest.update(chunk)
                if digest.hexdigest() != validated.manifest.files[member].sha256:
                    raise SignalReviewBundleError(f"Bundle source changed while extracting {timeframe}")
                frame = load_ohlcv_csv(target, timeframe)
                current = source_metadata(target, frame, timeframe, include_sha256=True)
                expected = validated.payload.run.source_metadata[timeframe]
                for key in ("row_count", "available_start", "available_end", "sha256"):
                    if expected.get(key) != current.get(key):
                        raise SignalReviewBundleError(f"Imported {timeframe} source does not match its replay facts")
                frames[timeframe] = frame

        if final_dir.exists():
            for name, record in validated.manifest.files.items():
                existing = final_dir / name
                if (
                    not existing.is_file()
                    or existing.stat().st_size != record.size
                    or _sha256_file(existing) != record.sha256
                ):
                    raise SignalReviewBundleError("An incomplete import already occupies this bundle identity")
        else:
            os.replace(staging, final_dir)
            created = True
        source_facts: dict[str, Any] = {}
        for timeframe, member in SOURCE_MEMBERS.items():
            source_path = final_dir / member
            frame = frames[timeframe] if created else load_ohlcv_csv(source_path, timeframe)
            facts = source_metadata(source_path, frame, timeframe, include_sha256=True)
            original = validated.payload.run.source_metadata[timeframe]
            facts["original_filename"] = original.get("filename")
            facts["original_source_modified_at"] = original.get("source_modified_at")
            source_facts[timeframe] = facts
        return final_dir, created, source_facts
    except Exception:
        if created:
            shutil.rmtree(final_dir, ignore_errors=True)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _new_signal_row(record: _BundleSignal) -> SignalReplaySignal:
    row = SignalReplaySignal(
        event_id=record.event_id,
        sequence=record.sequence,
        timeframe=record.timeframe,
        definition_version=record.definition_version,
        trigger_open_at=_utc_naive(record.trigger_open_at),
        trigger_close_at=_utc_naive(record.trigger_close_at),
        trigger_close_price=record.trigger_close_price,
        trigger_price_ema21=record.trigger_price_ema21,
        rsi21=record.rsi21,
        rsi_ema9=record.rsi_ema9,
        rsi_wma45=record.rsi_wma45,
        rsi_spread=record.rsi_spread,
        previous_rsi_ema9=record.previous_rsi_ema9,
        previous_rsi_wma45=record.previous_rsi_wma45,
        h4_close_price=record.h4_close_price,
        h4_price_ema21=record.h4_price_ema21,
        h4_close_at=_utc_naive(record.h4_close_at),
        decision_reason=record.decision_reason,
        telegram_card=record.telegram_card,
        snapshot=record.snapshot,
    )
    review = record.review
    row.review = SignalReview(
        quality=review.quality,
        human_outcome=review.human_outcome,
        note=review.note,
        reviewed_at=_utc_naive(review.reviewed_at),
        updated_at=_utc_naive(review.updated_at) or datetime.now(UTC).replace(tzinfo=None),
        future_unlocked_at=_utc_naive(review.future_unlocked_at),
        take_profit_price=review.take_profit_price,
        stop_loss_price=review.stop_loss_price,
        exit_reason=review.exit_reason,
        exit_at=_utc_naive(review.exit_at),
        duration_minutes=review.duration_minutes,
        evaluation_warning=review.evaluation_warning,
        evaluated_at=_utc_naive(review.evaluated_at),
    )
    for metric in record.forward_metrics:
        row.forward_metrics.append(
            SignalForwardMetric(
                horizon_minutes=metric.horizon_minutes,
                price_at_observation=metric.price_at_observation,
                return_pct=metric.return_pct,
                mfe_pct=metric.mfe_pct,
                mae_pct=metric.mae_pct,
                observed_at=_utc_naive(metric.observed_at),
                complete=metric.complete,
                warning=metric.warning,
            )
        )
    return row


def import_signal_review_bundle(
    archive_path: Path,
    db: Session,
    *,
    import_root: Path | None = None,
) -> BundleImportResult:
    """Validate and import a bundle as a separate immutable local replay run."""

    validated = _validate_archive(archive_path)
    manifest = validated.manifest
    existing = _find_existing_import(db, manifest.bundle_id)
    if existing is not None:
        return BundleImportResult(
            run_id=existing.id,
            bundle_id=manifest.bundle_id,
            duplicate=True,
            signal_count=manifest.counts.signal_count,
            reviewed_count=manifest.counts.reviewed_count,
            source_run_id=manifest.source_run_id,
        )

    root = import_root or IMPORT_ROOT
    final_dir, created_directory, source_facts = _extract_bundle_sources(archive_path, validated, root)
    try:
        source_run = validated.payload.run
        now = datetime.now(UTC).replace(tzinfo=None)
        source_facts["_review_bundle"] = {
            "bundle_id": manifest.bundle_id,
            "format_version": manifest.format_version,
            "source_run_id": manifest.source_run_id,
            "source_created_at": _iso(source_run.created_at),
            "source_started_at": _iso(source_run.started_at),
            "source_completed_at": _iso(source_run.completed_at),
            "exported_at": _iso(manifest.exported_at),
            "imported_at": _iso(now),
            "warnings": manifest.warnings,
        }
        run = SignalReplayRun(
            status="completed",
            strategy_name=source_run.strategy_name,
            definition_version=source_run.definition_version,
            git_hash=source_run.git_hash,
            symbol=source_run.symbol,
            requested_start_at=_utc_naive(source_run.requested_start_at),
            requested_end_at=_utc_naive(source_run.requested_end_at),
            created_at=now,
            started_at=now,
            completed_at=now,
            source_metadata=source_facts,
            counters=source_run.counters,
            error_message=None,
        )
        run.signals.extend(_new_signal_row(record) for record in validated.payload.signals)
        db.add(run)
        db.commit()
        db.refresh(run)
    except Exception:
        db.rollback()
        if created_directory:
            shutil.rmtree(final_dir, ignore_errors=True)
        raise
    return BundleImportResult(
        run_id=run.id,
        bundle_id=manifest.bundle_id,
        duplicate=False,
        signal_count=manifest.counts.signal_count,
        reviewed_count=manifest.counts.reviewed_count,
        source_run_id=manifest.source_run_id,
    )
