"""Portable Signal Review bundle export/import and API regressions."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.main import app
from app.api.routes import signal_replays
from app.backtest.signal_replay_analysis import source_metadata
from app.backtest.signal_replay_bundle import (
    create_signal_review_bundle,
    import_signal_review_bundle,
)
from app.backtest.signal_replay_bundle_format import (
    EXPECTED_MEMBERS,
    SignalReviewBundleError,
)
from app.backtest.signal_replay_data import load_ohlcv_csv
from app.repository.backtest.database import Base
from app.repository.backtest.models import (
    SignalForwardMetric,
    SignalReplayRun,
    SignalReplaySignal,
    SignalReview,
)


def _session_factory(path: Path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine)


def _write_source(path: Path, *, minutes: int) -> None:
    timestamps = pd.date_range("2026-01-01 00:00:00", periods=16, freq=f"{minutes}min")
    prices = [100.0 + position for position in range(len(timestamps))]
    pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": prices,
            "high": [price + 1.0 for price in prices],
            "low": [price - 1.0 for price in prices],
            "close": prices,
            "volume": [1.0] * len(prices),
        }
    ).to_csv(path, index=False)


def _source_paths(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "5m": root / "BTCUSDT_5m.csv",
        "15m": root / "BTCUSDT_15m.csv",
        "1h": root / "BTCUSDT_1h.csv",
        "4h": root / "BTCUSDT_4h.csv",
    }
    for timeframe, minutes in (("5m", 5), ("15m", 15), ("1h", 60), ("4h", 240)):
        _write_source(paths[timeframe], minutes=minutes)
    return paths


def _seed_run(db: Session, source_root: Path) -> SignalReplayRun:
    paths = _source_paths(source_root)
    facts = {
        timeframe: source_metadata(
            path,
            load_ohlcv_csv(path, timeframe),
            timeframe,
            include_sha256=True,
        )
        for timeframe, path in paths.items()
    }
    created_at = datetime(2026, 1, 2, 12, 0)
    run = SignalReplayRun(
        status="completed",
        strategy_name="btc_rsi_cross_alert",
        definition_version="btc-rsi-cross-v1",
        git_hash="a" * 40,
        symbol="BTC/USDT",
        requested_start_at=datetime(2026, 1, 1),
        requested_end_at=datetime(2026, 1, 2),
        created_at=created_at,
        started_at=created_at,
        completed_at=created_at + timedelta(minutes=1),
        source_metadata=facts,
        counters={"signals": 1, "m5_signals": 1, "m15_signals": 0},
    )
    signal = SignalReplaySignal(
        event_id="btc-review-event-1",
        sequence=1,
        timeframe="5m",
        definition_version="btc-rsi-cross-v1",
        trigger_open_at=datetime(2026, 1, 1, 0, 5),
        trigger_close_at=datetime(2026, 1, 1, 0, 10),
        trigger_close_price="102.0",
        trigger_price_ema21="101.0",
        rsi21=55.0,
        rsi_ema9=51.0,
        rsi_wma45=50.0,
        rsi_spread=1.0,
        previous_rsi_ema9=None,
        previous_rsi_wma45=None,
        h4_close_price="105.0",
        h4_price_ema21="100.0",
        h4_close_at=datetime(2026, 1, 1, 0, 0),
        decision_reason="TEST_CONFIRMATION",
        telegram_card="BTC test card",
        snapshot={"snapshot_version": "btc-rsi-cross-v1", "test": True},
    )
    signal.review = SignalReview(
        quality="GOOD",
        human_outcome="WIN",
        note="Reviewed on the source machine",
        reviewed_at=created_at + timedelta(minutes=2),
        updated_at=created_at + timedelta(minutes=2),
        future_unlocked_at=created_at + timedelta(minutes=2),
        take_profit_price="110.0",
        stop_loss_price="95.0",
        exit_reason="TAKE_PROFIT",
        exit_at=datetime(2026, 1, 1, 1, 10),
        duration_minutes=60,
        evaluated_at=created_at + timedelta(minutes=2),
    )
    signal.forward_metrics.append(
        SignalForwardMetric(
            horizon_minutes=60,
            price_at_observation="110.0",
            return_pct=7.843137,
            mfe_pct=8.0,
            mae_pct=-1.0,
            observed_at=datetime(2026, 1, 1, 1, 10),
            complete=True,
        )
    )
    run.signals.append(signal)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _rewrite_archive(source: Path, destination: Path, *, tamper_review: bool = False, add_extra: bool = False) -> None:
    with (
        zipfile.ZipFile(source, "r") as original,
        zipfile.ZipFile(
            destination,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as rewritten,
    ):
        for name in original.namelist():
            data = original.read(name)
            if tamper_review and name == "review.json":
                data = data.replace(b'"GOOD"', b'"BAD!"', 1)
            rewritten.writestr(name, data)
        if add_extra:
            rewritten.writestr("../unexpected.txt", b"must not be extracted")


def test_bundle_round_trip_preserves_review_and_is_duplicate_safe(tmp_path):
    source_engine, source_factory = _session_factory(tmp_path / "source.db")
    target_engine, target_factory = _session_factory(tmp_path / "target.db")
    source_db = source_factory()
    target_db = target_factory()
    try:
        source_run = _seed_run(source_db, tmp_path / "source-data")
        artifact = create_signal_review_bundle(
            source_run.id,
            source_db,
            output_dir=tmp_path,
            allowed_source_roots=(tmp_path / "source-data",),
        )

        with zipfile.ZipFile(artifact.path, "r") as archive:
            assert set(archive.namelist()) == EXPECTED_MEMBERS
            manifest = json.loads(archive.read("manifest.json"))
            review_payload = archive.read("review.json").decode("utf-8")
        assert manifest["bundle_id"] == artifact.bundle_id
        assert manifest["counts"] == {
            "signal_count": 1,
            "reviewed_count": 1,
            "m5_count": 1,
            "m15_count": 0,
        }
        assert str(tmp_path) not in review_payload

        imported = import_signal_review_bundle(
            artifact.path,
            target_db,
            import_root=tmp_path / "imports",
        )
        assert imported.duplicate is False
        imported_run = target_db.query(SignalReplayRun).filter_by(id=imported.run_id).one()
        assert imported_run.id != source_run.id or source_db.bind is not target_db.bind
        assert imported_run.git_hash == "a" * 40
        assert imported_run.source_metadata["_review_bundle"]["bundle_id"] == artifact.bundle_id
        assert Path(imported_run.source_metadata["5m"]["path"]).is_file()
        assert (tmp_path / "imports" / artifact.bundle_id / "review.json").is_file()
        imported_signal = imported_run.signals[0]
        assert imported_signal.event_id == "btc-review-event-1"
        assert imported_signal.review.quality == "GOOD"
        assert imported_signal.review.human_outcome == "WIN"
        assert imported_signal.review.note == "Reviewed on the source machine"
        assert imported_signal.forward_metrics[0].horizon_minutes == 60

        duplicate = import_signal_review_bundle(
            artifact.path,
            target_db,
            import_root=tmp_path / "imports",
        )
        assert duplicate.duplicate is True
        assert duplicate.run_id == imported.run_id
        assert target_db.query(SignalReplayRun).count() == 1
    finally:
        source_db.close()
        target_db.close()
        Base.metadata.drop_all(bind=source_engine)
        Base.metadata.drop_all(bind=target_engine)


@pytest.mark.parametrize(
    ("tamper_review", "add_extra", "message"),
    [
        (True, False, "hash check failed"),
        (False, True, "unexpected files"),
    ],
)
def test_bundle_rejects_tampering_and_unexpected_members(
    tmp_path,
    tamper_review,
    add_extra,
    message,
):
    engine, factory = _session_factory(tmp_path / "database.db")
    db = factory()
    try:
        run = _seed_run(db, tmp_path / "source-data")
        artifact = create_signal_review_bundle(
            run.id,
            db,
            output_dir=tmp_path,
            allowed_source_roots=(tmp_path / "source-data",),
        )
        bad_bundle = tmp_path / "bad.zip"
        _rewrite_archive(
            artifact.path,
            bad_bundle,
            tamper_review=tamper_review,
            add_extra=add_extra,
        )

        with pytest.raises(SignalReviewBundleError, match=message):
            import_signal_review_bundle(bad_bundle, db, import_root=tmp_path / "imports")
        assert not (tmp_path / "unexpected.txt").exists()
        assert db.query(SignalReplayRun).count() == 1
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_export_fails_closed_when_replay_source_bytes_change(tmp_path):
    engine, factory = _session_factory(tmp_path / "database.db")
    db = factory()
    try:
        run = _seed_run(db, tmp_path / "source-data")
        with (tmp_path / "source-data" / "BTCUSDT_5m.csv").open("ab") as handle:
            handle.write(b"\n")

        with pytest.raises(SignalReviewBundleError, match="source hash changed"):
            create_signal_review_bundle(
                run.id,
                db,
                output_dir=tmp_path,
                allowed_source_roots=(tmp_path / "source-data",),
            )
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_legacy_run_without_replay_hash_exports_with_manifest_warning(tmp_path):
    engine, factory = _session_factory(tmp_path / "database.db")
    db = factory()
    try:
        run = _seed_run(db, tmp_path / "source-data")
        run.source_metadata = {
            timeframe: {key: value for key, value in facts.items() if key != "sha256"}
            for timeframe, facts in run.source_metadata.items()
        }
        db.commit()

        artifact = create_signal_review_bundle(
            run.id,
            db,
            output_dir=tmp_path,
            allowed_source_roots=(tmp_path / "source-data",),
        )
        with zipfile.ZipFile(artifact.path, "r") as archive:
            manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["warnings"]) == 4
        assert all("before replay-time hashing" in warning for warning in manifest["warnings"])
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_bundle_api_downloads_and_imports_one_zip(tmp_path, monkeypatch):
    engine, factory = _session_factory(tmp_path / "api.db")

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    def export_for_test(run_id, db):
        return create_signal_review_bundle(
            run_id,
            db,
            output_dir=tmp_path,
            allowed_source_roots=(tmp_path / "source-data", tmp_path / "imports"),
        )

    def import_for_test(path, db):
        return import_signal_review_bundle(path, db, import_root=tmp_path / "imports")

    app.dependency_overrides[signal_replays.get_db] = override_get_db
    monkeypatch.setattr(signal_replays, "create_signal_review_bundle", export_for_test)
    monkeypatch.setattr(signal_replays, "import_signal_review_bundle", import_for_test)
    db = factory()
    try:
        source_run = _seed_run(db, tmp_path / "source-data")
        client = TestClient(app)
        download = client.get(f"/api/signal-replays/runs/{source_run.id}/bundle")
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"
        assert "BTC-signal-review" in download.headers["content-disposition"]

        imported = client.post(
            "/api/signal-replays/bundles/import",
            content=download.content,
            headers={"Content-Type": "application/zip"},
        )
        assert imported.status_code == 200
        body = imported.json()
        assert body["duplicate"] is False
        assert body["signal_count"] == 1
        assert body["reviewed_count"] == 1

        repeated = client.post(
            "/api/signal-replays/bundles/import",
            content=download.content,
            headers={"Content-Type": "application/zip"},
        )
        assert repeated.status_code == 200
        assert repeated.json()["duplicate"] is True
        assert repeated.json()["run_id"] == body["run_id"]

        empty = client.post(
            "/api/signal-replays/bundles/import",
            content=b"",
            headers={"Content-Type": "application/zip"},
        )
        assert empty.status_code == 400
        assert "empty" in empty.json()["detail"]
    finally:
        app.dependency_overrides.pop(signal_replays.get_db, None)
        db.close()
        Base.metadata.drop_all(bind=engine)
