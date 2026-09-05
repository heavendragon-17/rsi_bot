"""SQLite persistence for campaigns and resumable pipeline state."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .contracts import canonical_json


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class PipelineStore:
    """Small SQLite repository; each mutation commits atomically."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
                    question TEXT NOT NULL, config_json TEXT NOT NULL, context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS budgets (
                    campaign_id TEXT PRIMARY KEY REFERENCES campaigns(id),
                    max_thinker_calls INTEGER NOT NULL, max_executor_calls INTEGER NOT NULL,
                    max_jobs INTEGER NOT NULL, thinker_calls INTEGER NOT NULL DEFAULT 0,
                    executor_calls INTEGER NOT NULL DEFAULT 0, jobs_started INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    parent_job_id TEXT REFERENCES jobs(id), sequence INTEGER NOT NULL,
                    status TEXT NOT NULL, specification_json TEXT NOT NULL, specification_hash TEXT NOT NULL,
                    result_id TEXT, budget_reserved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    job_id TEXT REFERENCES jobs(id), role TEXT NOT NULL, phase TEXT NOT NULL,
                    provider TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
                    request_json TEXT NOT NULL, response_json TEXT, usage_json TEXT,
                    error_kind TEXT, error_message TEXT, started_at TEXT NOT NULL, finished_at TEXT,
                    elapsed_ms REAL
                );
                CREATE TABLE IF NOT EXISTS results (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                    status TEXT NOT NULL, artifact_dir TEXT NOT NULL, evidence_json TEXT NOT NULL,
                    result_hash TEXT NOT NULL, cache_key TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    job_id TEXT NOT NULL REFERENCES jobs(id), phase TEXT NOT NULL,
                    action TEXT NOT NULL, reasons_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
                    next_job_id TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS failures (
                    id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    job_id TEXT, attempt_id TEXT, kind TEXT NOT NULL, message TEXT NOT NULL,
                    retryable INTEGER NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_campaign ON jobs(campaign_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_attempts_campaign ON attempts(campaign_id, started_at);
                CREATE INDEX IF NOT EXISTS idx_decisions_campaign ON decisions(campaign_id, created_at);
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(attempts)")}
            if "elapsed_ms" not in columns:
                db.execute("ALTER TABLE attempts ADD COLUMN elapsed_ms REAL")
            job_columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            if "budget_reserved" not in job_columns:
                db.execute("ALTER TABLE jobs ADD COLUMN budget_reserved INTEGER NOT NULL DEFAULT 0")
            result_columns = {row[1] for row in db.execute("PRAGMA table_info(results)")}
            if "cache_key" not in result_columns:
                db.execute("ALTER TABLE results ADD COLUMN cache_key TEXT")
            db.execute("CREATE INDEX IF NOT EXISTS idx_results_cache ON results(cache_key)")

    @staticmethod
    def _json(value: Any) -> str:
        return canonical_json(value)

    def create_campaign(self, campaign_id: str, name: str, question: str, config: dict[str, Any], context: dict[str, Any]) -> None:
        timestamp = now_iso()
        with self.connection() as db:
            db.execute("INSERT INTO campaigns VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (campaign_id, name, "RUNNING", question, self._json(config), self._json(context), timestamp, timestamp))
            db.execute("INSERT INTO budgets VALUES (?, ?, ?, ?, 0, 0, 0, ?)", (campaign_id, config["max_thinker_calls"], config["max_executor_calls"], config["max_jobs"], timestamp))

    def campaign(self, campaign_id: str) -> sqlite3.Row:
        with self.connection() as db:
            row = db.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if row is None:
            raise KeyError(f"campaign not found: {campaign_id}")
        return row

    def config(self, campaign_id: str) -> dict[str, Any]:
        import json
        return json.loads(self.campaign(campaign_id)["config_json"])

    def context(self, campaign_id: str) -> dict[str, Any]:
        import json
        return json.loads(self.campaign(campaign_id)["context_json"])

    def set_campaign_status(self, campaign_id: str, status: str) -> None:
        with self.connection() as db:
            db.execute("UPDATE campaigns SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), campaign_id))

    def budget(self, campaign_id: str) -> sqlite3.Row:
        with self.connection() as db:
            return db.execute("SELECT * FROM budgets WHERE campaign_id = ?", (campaign_id,)).fetchone()

    def reserve_call(self, campaign_id: str, role: str) -> None:
        column = "thinker_calls" if role == "thinker" else "executor_calls"
        limit_column = "max_thinker_calls" if role == "thinker" else "max_executor_calls"
        with self.connection() as db:
            updated = db.execute(f"UPDATE budgets SET {column} = {column} + 1, updated_at = ? WHERE campaign_id = ? AND {column} < {limit_column}", (now_iso(), campaign_id))  # nosec B608: column names are fixed above
            if updated.rowcount != 1:
                raise RuntimeError(f"{role} budget exhausted")

    def reserve_job(self, campaign_id: str) -> None:
        with self.connection() as db:
            updated = db.execute("UPDATE budgets SET jobs_started = jobs_started + 1, updated_at = ? WHERE campaign_id = ? AND jobs_started < max_jobs", (now_iso(), campaign_id))
            if updated.rowcount != 1:
                raise RuntimeError("job budget exhausted")

    def create_job(self, job_id: str, campaign_id: str, sequence: int, specification: dict[str, Any], specification_hash: str, parent_job_id: str | None = None, status: str = "PROPOSED", *, budget_reserved: bool = False) -> None:
        timestamp = now_iso()
        with self.connection() as db:
            db.execute("INSERT INTO jobs (id, campaign_id, parent_job_id, sequence, status, specification_json, specification_hash, result_id, budget_reserved, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (job_id, campaign_id, parent_job_id, sequence, status, self._json(specification), specification_hash, None, int(budget_reserved), timestamp, timestamp))

    def create_initial_job(self, job_id: str, campaign_id: str, sequence: int, specification: dict[str, Any], specification_hash: str, *, status: str = "PROPOSING") -> None:
        """Reserve and create the first job in one transaction."""

        self.ensure_initial_job(job_id, campaign_id, sequence, specification, specification_hash, status=status)

    def ensure_initial_job(self, job_id: str, campaign_id: str, sequence: int, specification: dict[str, Any], specification_hash: str, *, status: str = "PROPOSING") -> str:
        """Return the campaign's one root job, creating it atomically."""

        timestamp = now_iso()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id FROM jobs WHERE campaign_id = ? AND parent_job_id IS NULL ORDER BY sequence LIMIT 1", (campaign_id,)).fetchone()
            if existing is not None:
                return str(existing["id"])
            updated = db.execute("UPDATE budgets SET jobs_started = jobs_started + 1, updated_at = ? WHERE campaign_id = ? AND jobs_started < max_jobs", (timestamp, campaign_id))
            if updated.rowcount != 1:
                raise RuntimeError("job budget exhausted")
            db.execute("INSERT INTO jobs (id, campaign_id, parent_job_id, sequence, status, specification_json, specification_hash, result_id, budget_reserved, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)", (job_id, campaign_id, None, sequence, status, self._json(specification), specification_hash, None, timestamp, timestamp))
        return job_id

    def create_followup_job(self, job_id: str, campaign_id: str, sequence: int, specification: dict[str, Any], specification_hash: str, parent_job_id: str) -> str:
        """Create a follow-up and reserve it only when the job cap allows it.

        Repeated calls for the same parent are idempotent. The controller uses
        :meth:`ensure_followup_job` when it also needs the durable job ID.
        """

        _, status = self.ensure_followup_job(job_id, campaign_id, sequence, specification, specification_hash, parent_job_id)
        return status

    def ensure_followup_job(self, job_id: str, campaign_id: str, sequence: int, specification: dict[str, Any], specification_hash: str, parent_job_id: str) -> tuple[str, str]:
        """Return one durable child for a parent, creating it atomically."""

        timestamp = now_iso()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id, status FROM jobs WHERE campaign_id = ? AND parent_job_id = ? ORDER BY sequence LIMIT 1", (campaign_id, parent_job_id)).fetchone()
            if existing is not None:
                return str(existing["id"]), str(existing["status"])
            updated = db.execute("UPDATE budgets SET jobs_started = jobs_started + 1, updated_at = ? WHERE campaign_id = ? AND jobs_started < max_jobs", (timestamp, campaign_id))
            reserved = updated.rowcount == 1
            status = "PROPOSED" if reserved else "DEFERRED_LIMIT"
            db.execute("INSERT INTO jobs (id, campaign_id, parent_job_id, sequence, status, specification_json, specification_hash, result_id, budget_reserved, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (job_id, campaign_id, parent_job_id, sequence, status, self._json(specification), specification_hash, None, int(reserved), timestamp, timestamp))
        return job_id, status

    def job(self, job_id: str) -> sqlite3.Row:
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"job not found: {job_id}")
        return row

    def jobs(self, campaign_id: str) -> list[sqlite3.Row]:
        with self.connection() as db:
            return list(db.execute("SELECT * FROM jobs WHERE campaign_id = ? ORDER BY sequence", (campaign_id,)))

    def claim_job_reservation(self, job_id: str) -> bool:
        """Idempotently claim a deferred/legacy job reservation."""

        timestamp = now_iso()
        with self.connection() as db:
            # Serialize the read/conditional budget increment/job mark pair.
            # Without an immediate write transaction, two resumptions could
            # both observe an unreserved job and increment the job counter
            # before either one marks it claimed.
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT campaign_id, status, budget_reserved FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                raise KeyError(f"job not found: {job_id}")
            if job["budget_reserved"]:
                return True
            if job["status"] not in {"DEFERRED_LIMIT", "PROPOSING", "PROPOSED"}:
                return False
            updated = db.execute("UPDATE budgets SET jobs_started = jobs_started + 1, updated_at = ? WHERE campaign_id = ? AND jobs_started < max_jobs", (timestamp, job["campaign_id"]))
            if updated.rowcount != 1:
                return False
            marked = db.execute("UPDATE jobs SET budget_reserved = 1, status = CASE WHEN status = 'DEFERRED_LIMIT' THEN 'PROPOSED' ELSE status END, updated_at = ? WHERE id = ? AND budget_reserved = 0", (timestamp, job_id))
            if marked.rowcount != 1:
                raise RuntimeError("job reservation mark failed; transaction rolled back")
            return True

    def update_job(self, job_id: str, *, status: str | None = None, result_id: str | None = None) -> None:
        updates, values = [], []
        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if result_id is not None:
            updates.append("result_id = ?")
            values.append(result_id)
        if updates:
            values.extend([now_iso(), job_id])
            with self.connection() as db:
                db.execute(f"UPDATE jobs SET {', '.join(updates)}, updated_at = ? WHERE id = ?", values)  # nosec B608: clauses are fixed above

    def update_job_specification(self, job_id: str, specification: dict[str, Any], specification_hash: str) -> None:
        with self.connection() as db:
            db.execute("UPDATE jobs SET specification_json = ?, specification_hash = ?, updated_at = ? WHERE id = ?", (self._json(specification), specification_hash, now_iso(), job_id))

    def create_attempt(self, attempt_id: str, campaign_id: str, job_id: str, role: str, phase: str, provider: str, model: str, request: dict[str, Any]) -> None:
        with self.connection() as db:
            db.execute("INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (attempt_id, campaign_id, job_id, role, phase, provider, model, "RUNNING", self._json(request), None, None, None, None, now_iso(), None, None))

    def finish_attempt(self, attempt_id: str, *, status: str, response: Any = None, usage: Any = None, error_kind: str | None = None, error_message: str | None = None) -> None:
        with self.connection() as db:
            finished = now_iso()
            row = db.execute("SELECT started_at FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
            elapsed_ms = None
            if row and row[0]:
                elapsed_ms = max(0.0, (datetime.fromisoformat(finished.replace("Z", "+00:00")) - datetime.fromisoformat(row[0].replace("Z", "+00:00"))).total_seconds() * 1000)
            db.execute("UPDATE attempts SET status = ?, response_json = ?, usage_json = ?, error_kind = ?, error_message = ?, finished_at = ?, elapsed_ms = ? WHERE id = ? AND status = 'RUNNING'", (status, self._json(response) if response is not None else None, self._json(usage) if usage is not None else None, error_kind, error_message, finished, elapsed_ms, attempt_id))

    def running_attempts(self, campaign_id: str) -> list[sqlite3.Row]:
        with self.connection() as db:
            return list(db.execute("SELECT * FROM attempts WHERE campaign_id = ? AND status = 'RUNNING'", (campaign_id,)))

    def completed_attempt(self, campaign_id: str, job_id: str, phase: str) -> sqlite3.Row | None:
        with self.connection() as db:
            return db.execute("SELECT * FROM attempts WHERE campaign_id = ? AND job_id = ? AND phase = ? AND status = 'COMPLETED' AND response_json IS NOT NULL ORDER BY finished_at DESC LIMIT 1", (campaign_id, job_id, phase)).fetchone()

    def uncertain_attempts(self, campaign_id: str) -> list[sqlite3.Row]:
        with self.connection() as db:
            return list(db.execute("SELECT * FROM attempts WHERE campaign_id = ? AND status = 'PAUSED' AND error_kind = 'interrupted_uncertain' ORDER BY started_at", (campaign_id,)))

    def reconcile_uncertain_attempts(self, campaign_id: str) -> int:
        with self.connection() as db:
            updated = db.execute("UPDATE attempts SET status = 'RECONCILED' WHERE campaign_id = ? AND status = 'PAUSED' AND error_kind = 'interrupted_uncertain'", (campaign_id,))
            return updated.rowcount

    def create_result(self, result_id: str, job_id: str, status: str, artifact_dir: str, evidence: dict[str, Any], result_hash: str, cache_key: str | None = None) -> None:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM results WHERE job_id = ?", (job_id,)).fetchone()
            if existing is not None:
                return
            db.execute("INSERT INTO results (id, job_id, status, artifact_dir, evidence_json, result_hash, cache_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (result_id, job_id, status, artifact_dir, self._json(evidence), result_hash, cache_key, now_iso()))
            db.execute("UPDATE jobs SET result_id = ?, status = 'CHECKED', updated_at = ? WHERE id = ? AND result_id IS NULL", (result_id, now_iso(), job_id))

    def cached_result(self, cache_key: str) -> sqlite3.Row | None:
        """Return one previously verified result with the same immutable identity."""

        with self.connection() as db:
            return db.execute("SELECT * FROM results WHERE cache_key = ? AND status = 'VERIFIED' ORDER BY created_at LIMIT 1", (cache_key,)).fetchone()

    def result(self, result_id: str) -> sqlite3.Row:
        with self.connection() as db:
            row = db.execute("SELECT * FROM results WHERE id = ?", (result_id,)).fetchone()
        if row is None:
            raise KeyError(f"result not found: {result_id}")
        return row

    def result_for_job(self, job_id: str) -> sqlite3.Row | None:
        with self.connection() as db:
            return db.execute("SELECT * FROM results WHERE job_id = ? ORDER BY created_at LIMIT 1", (job_id,)).fetchone()

    def create_decision(self, decision_id: str, campaign_id: str, job_id: str, phase: str, action: str, reasons: list[str], evidence: dict[str, Any], next_job_id: str | None = None) -> None:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id FROM decisions WHERE campaign_id = ? AND job_id = ? AND phase = ?", (campaign_id, job_id, phase)).fetchone()
            if existing is not None:
                return
            db.execute("INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (decision_id, campaign_id, job_id, phase, action, self._json(reasons), self._json(evidence), next_job_id, now_iso()))

    def decisions(self, campaign_id: str) -> list[sqlite3.Row]:
        with self.connection() as db:
            return list(db.execute("SELECT * FROM decisions WHERE campaign_id = ? ORDER BY created_at", (campaign_id,)))

    def decision_for_job(self, campaign_id: str, job_id: str, phase: str = "review") -> sqlite3.Row | None:
        with self.connection() as db:
            return db.execute("SELECT * FROM decisions WHERE campaign_id = ? AND job_id = ? AND phase = ? ORDER BY created_at LIMIT 1", (campaign_id, job_id, phase)).fetchone()

    def followup_for_parent(self, campaign_id: str, parent_job_id: str) -> sqlite3.Row | None:
        with self.connection() as db:
            return db.execute("SELECT * FROM jobs WHERE campaign_id = ? AND parent_job_id = ? ORDER BY sequence LIMIT 1", (campaign_id, parent_job_id)).fetchone()

    def create_failure(self, failure_id: str, campaign_id: str, *, job_id: str | None, attempt_id: str | None, kind: str, message: str, retryable: bool, details: dict[str, Any] | None = None) -> None:
        with self.connection() as db:
            db.execute("INSERT INTO failures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (failure_id, campaign_id, job_id, attempt_id, kind, message, int(retryable), self._json(details or {}), now_iso()))

    def failures(self, campaign_id: str) -> list[sqlite3.Row]:
        with self.connection() as db:
            return list(db.execute("SELECT * FROM failures WHERE campaign_id = ? ORDER BY created_at", (campaign_id,)))

    def summary(self, campaign_id: str) -> dict[str, Any]:
        campaign = self.campaign(campaign_id)
        budget = self.budget(campaign_id)
        return {"campaign": dict(campaign), "budget": dict(budget), "jobs": [dict(row) for row in self.jobs(campaign_id)], "attempts": self._rows("SELECT * FROM attempts WHERE campaign_id = ? ORDER BY started_at", campaign_id), "results": self._rows("SELECT r.* FROM results r JOIN jobs j ON j.id = r.job_id WHERE j.campaign_id = ? ORDER BY r.created_at", campaign_id), "decisions": [dict(row) for row in self.decisions(campaign_id)], "failures": [dict(row) for row in self.failures(campaign_id)]}

    def _rows(self, query: str, campaign_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(query, (campaign_id,))]
