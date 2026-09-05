"""Synthetic adaptive providers exercise read-only benchmark provenance, never live models."""

import hashlib
import importlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from test_btc_ai_pipeline_adaptive import adaptive_config

from app.research_pipeline.adaptive_fixture import AdaptiveFixtureProvider
from app.research_pipeline.contracts import object_hash
from app.research_pipeline.controller import PipelineController


class SyntheticLiveLabels(AdaptiveFixtureProvider):
    """Only a local fixture; provider labels simulate a persisted live record."""

    def complete(self, request):
        response = super().complete(request)
        payload = response.payload
        if request.phase == "execution" and payload["task"] == "compare_m5_cohorts":
            payload["parameters"]["grouping"] = "volatility"
        return replace(response, provider="codex" if request.role == "thinker" else "opencode")


@pytest.fixture
def campaign(tmp_path):
    cfg = adaptive_config(tmp_path, thinker_provider="codex", executor_provider="opencode", live_opt_in=True)
    controller = PipelineController(cfg, thinkers={"codex": SyntheticLiveLabels("thinker")},
                                    executors={"opencode": SyntheticLiveLabels("executor")})
    identifier = controller.create_campaign(name="synthetic provenance fixture; no live calls")
    state = controller.run(identifier)
    assert state["status"] == "STOPPED", state["failures"]
    return Path(cfg.repo_root), Path(cfg.db_path), identifier


def module():
    assert importlib.util.find_spec("app.research_pipeline.benchmark_source") is not None, "source loader not implemented"
    return importlib.import_module("app.research_pipeline.benchmark_source")


def mutate(db_path, sql, params=()):
    with sqlite3.connect(db_path) as db:
        db.execute(sql, params)


def test_load_freezes_distinct_choice_and_does_not_write_source(campaign):
    root, db, identifier = campaign
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    source = module().load_benchmark_source(root, db, identifier)
    assert source["ai_parameters"]["grouping"] == "volatility"
    assert source["scripted_parameters"]["grouping"] == "calendar_year"
    assert source["source_hash"] == object_hash(source["summary"])
    assert len(source["artifacts"]) == 2
    json.dumps(source, allow_nan=False)
    module().verify_benchmark_source(source)
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    assert after == before


@pytest.mark.parametrize("sql,params", [
    ("UPDATE campaigns SET status='RUNNING'", ()),
    ("UPDATE jobs SET parent_job_id=NULL WHERE sequence=2", ()),
    ("UPDATE jobs SET specification_hash='bad' WHERE sequence=2", ()),
    ("UPDATE jobs SET result_id=(SELECT result_id FROM jobs WHERE sequence=1) WHERE sequence=2", ()),
    ("UPDATE attempts SET provider='fixture' WHERE phase='proposal'", ()),
    ("UPDATE attempts SET status='PAUSED' WHERE phase='proposal'", ()),
    ("UPDATE budgets SET thinker_calls=2", ()),
    ("UPDATE decisions SET next_job_id=NULL WHERE action='PROPOSE_NEXT'", ()),
    ("UPDATE results SET result_hash='bad'", ()),
])
def test_rejects_broken_chain(campaign, sql, params):
    root, db, identifier = campaign
    mutate(db, sql, params)
    with pytest.raises(ValueError):
        module().load_benchmark_source(root, db, identifier)


@pytest.mark.parametrize("kind", ["execution", "review", "proposal", "context"])
def test_rejects_json_valid_cross_record_drift(campaign, kind):
    root, db, identifier = campaign
    with sqlite3.connect(db) as connection:
        if kind == "context":
            value = json.loads(connection.execute("SELECT context_json FROM campaigns").fetchone()[0])
            value["evidence_hashes"]["source_sha256"] = "0" * 64
            connection.execute("UPDATE campaigns SET context_json=?", (json.dumps(value),))
        else:
            row = connection.execute("SELECT id,response_json FROM attempts WHERE phase=? ORDER BY started_at DESC", (kind,)).fetchone()
            value = json.loads(row[1])
            if kind == "execution":
                value["parameters"]["grouping"] = "trend"
            elif kind == "review":
                value["evidence_refs"] = ["result_wrong"]
            else:
                value["hypothesis"] = "A different but schema-valid hypothesis"
            connection.execute("UPDATE attempts SET response_json=? WHERE id=?", (json.dumps(value), row[0]))
    with pytest.raises(ValueError):
        module().load_benchmark_source(root, db, identifier)


def test_artifact_escape_and_artifact_drift_rejected(campaign, tmp_path):
    root, db, identifier = campaign
    outside = tmp_path / "outside"
    outside.mkdir()
    mutate(db, "UPDATE results SET artifact_dir=?", (str(outside),))
    with pytest.raises(ValueError, match="artifact"):
        module().load_benchmark_source(root, db, identifier)


def test_verify_detects_source_row_and_artifact_changes(campaign):
    root, db, identifier = campaign
    source = module().load_benchmark_source(root, db, identifier)
    mutate(db, "UPDATE campaigns SET name='changed after freezing'")
    with pytest.raises(ValueError, match="changed"):
        module().verify_benchmark_source(source)


def test_verify_detects_artifact_byte_change(campaign):
    root, db, identifier = campaign
    source = module().load_benchmark_source(root, db, identifier)
    artifact = Path(source["artifacts"][0]["path"])
    artifact.write_bytes(artifact.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="changed"):
        module().verify_benchmark_source(source)


def test_verify_detects_in_memory_choice_mutation(campaign):
    source = module().load_benchmark_source(*campaign)
    source["ai_parameters"]["grouping"] = "trend"
    with pytest.raises(ValueError, match="changed"):
        module().verify_benchmark_source(source)


def test_missing_database_is_not_created(tmp_path):
    db = tmp_path / "absent.sqlite"
    with pytest.raises(ValueError):
        module().load_benchmark_source(tmp_path, db, "campaign_missing")
    assert not db.exists()


def test_scripted_tie_break_and_nonfinite_rejection():
    evidence = {"task": "summarize_m5_horizons", "parameters": {"mode": "real"}, "tables": [
        {"horizon_minutes": h, "signal_minus_baseline_pp": gap}
        for h, gap in [(180, 2.0), (120, -2.0), (60, 1.0)]]}
    assert module().scripted_parameters(evidence) == {"mode": "real", "horizon_minutes": 120, "grouping": "calendar_year"}
    evidence["tables"][0]["signal_minus_baseline_pp"] = float("nan")
    with pytest.raises(ValueError):
        module().scripted_parameters(evidence)


def test_wal_changes_are_visible_and_unrelated_campaigns_do_not_change_hash(campaign):
    root, db, identifier = campaign
    source = module().load_benchmark_source(root, db, identifier)
    with sqlite3.connect(db) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO campaigns SELECT 'campaign_unrelated',name,status,question,config_json,context_json,created_at,updated_at FROM campaigns WHERE id=?", (identifier,))
        writer.commit()
        module().verify_benchmark_source(source)
        writer.execute("UPDATE campaigns SET name='change in WAL' WHERE id=?", (identifier,))
        writer.commit()
        with pytest.raises(ValueError, match="changed"):
            module().verify_benchmark_source(source)


@pytest.mark.parametrize("value", ["[]", '{"x":1,"x":2}', '{"x":1e999}'])
def test_malformed_context_is_rejected_as_source_error(campaign, value):
    root, db, identifier = campaign
    mutate(db, "UPDATE campaigns SET context_json=?", (value,))
    with pytest.raises(ValueError):
        module().load_benchmark_source(root, db, identifier)


@pytest.mark.parametrize("field,value", [("grouping", "trend"), ("signal_minus_baseline_pp", 123.0)])
def test_rehashed_but_structurally_wrong_tables_are_rejected(campaign, field, value):
    root, db, identifier = campaign
    with sqlite3.connect(db) as connection:
        row = connection.execute("SELECT r.id,r.evidence_json,r.artifact_dir FROM results r JOIN jobs j ON j.id=r.job_id WHERE j.sequence=2").fetchone()
        evidence = json.loads(row[1])
        evidence["tables"][0][field] = value
        base = {k: v for k, v in evidence.items() if k not in {
            "evidence_id", "checker_elapsed_seconds", "result_id", "reused_evidence", "executor_diagnostic", "cache_key"}}
        evidence["evidence_id"] = object_hash(base)
        connection.execute("UPDATE results SET evidence_json=?,result_hash=? WHERE id=?", (json.dumps(evidence), object_hash(evidence), row[0]))
        (Path(row[2]) / "evidence.json").write_text(json.dumps(evidence))
    with pytest.raises(ValueError):
        module().load_benchmark_source(root, db, identifier)
