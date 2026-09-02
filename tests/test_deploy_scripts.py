"""Functional regression tests for the deploy scripts' embedded Python.

The v1.2.8 release stalled on the VPS for ~10 hours because
``deploy/check_deploy.sh``'s ``write_state`` used ``tempfile.mkstemp``
without ``import tempfile``. The NameError only surfaces at runtime (bash
``-n`` and CI pass), and ``set -euo pipefail`` then killed the script
between the production checkout and ``deploy.sh`` — silently, because the
traceback went only to journald.

These tests extract the embedded-python helper functions from the deploy
scripts and execute them for real, so a missing import (or any runtime
regression in the helpers) fails CI."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_DIR = REPO_ROOT / "deploy"

CHECK_DEPLOY = (DEPLOY_DIR / "check_deploy.sh").read_text(encoding="utf-8")
DEPLOY_SH = (DEPLOY_DIR / "deploy.sh").read_text(encoding="utf-8")

_SCRIPT_SOURCES = {
    "check_deploy": CHECK_DEPLOY,
    "deploy": DEPLOY_SH,
}


def _bash_executable() -> str:
    """Return a Bash executable that can run from a Windows Python process."""

    if os.name == "nt":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates = (
            program_files / "Git" / "bin" / "bash.exe",
            program_files / "Git" / "usr" / "bin" / "bash.exe",
        )
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return shutil.which("bash") or "bash"


BASH = _bash_executable()


def _extract_function(script: str, name: str) -> str:
    """Extract a top-level bash function by brace counting.

    A simple ``^}``-anchored regex is not enough: the embedded Python in
    these helpers contains ``{``/``}`` at column 0 (dict literals), so the
    function body must run until brace depth returns to zero."""

    lines = script.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^{name}\(\) \{{\s*$", line):
            start = index
            break
    if start is None:
        raise AssertionError(f"function {name}() not found in deploy script")

    depth = 0
    body: list[str] = []
    for line in lines[start:]:
        depth += line.count("{") - line.count("}")
        body.append(line)
        if depth == 0:
            return "".join(body)
    raise AssertionError(f"function {name}() has unbalanced braces")


@pytest.fixture()
def bash_env(tmp_path: Path) -> dict[str, str]:
    """Environment with a ``python3`` shim pointing at the running
    interpreter (the deploy scripts call ``python3``; Windows Git Bash may
    not provide that name) and ``HARNESS_DIR`` at a scratch directory."""

    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "python3"
    shim.write_text(
        f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    env = os.environ.copy()
    if os.name == "nt":
        env["PATH"] = f"{shim_dir.as_posix()}:/usr/bin:/bin"
    else:
        env["PATH"] = f"{shim_dir}:{env.get('PATH', '')}"
    # Git Bash may not be able to create directories through its /c mount on
    # locked-down Windows hosts. A unique path relative to the checkout works
    # for Bash while retaining a native path for Python-side assertions.
    harness_name = f".deploy-test-harness-{tmp_path.name}"
    (REPO_ROOT / harness_name).mkdir(exist_ok=True)
    env["HARNESS_DIR"] = harness_name
    env["HARNESS_HOST_DIR"] = str(REPO_ROOT / harness_name)
    return env


def _run(
    harness_body: str,
    bash_env: dict[str, str],
    *functions: tuple[str, str],
) -> subprocess.CompletedProcess[str]:
    """Execute extracted deploy functions under production-like
    ``set -euo pipefail`` semantics with sandboxed paths. Each function is
    ``(script_key, function_name)``."""

    functions_src = "\n".join(
        _extract_function(_SCRIPT_SOURCES[key], name) for key, name in functions
    )
    setup = """set -euo pipefail
LOG_FILE="$HARNESS_DIR/deploy.log"
DEPLOY_STATE="$HARNESS_DIR/deploy_state.json"
STATUS_FILE="$HARNESS_DIR/status.json"
VERSION_FILE="$HARNESS_DIR/VERSION"
STALE_THRESHOLD="300"
export LOG_FILE DEPLOY_STATE STATUS_FILE VERSION_FILE STALE_THRESHOLD
log() { echo "[$(date -Iseconds)] $*" >> "$LOG_FILE"; }
"""
    script = f"{setup}\n{functions_src}\n\n{harness_body}\n"
    return subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        env=bash_env,
    )


class TestCheckDeployHelpers:
    def test_write_state_creates_valid_state_file(self, bash_env):
        """Regression: missing 'import tempfile' crashed write_state and,
        under set -e, killed check_deploy.sh before deploy.sh could run."""

        body = """
write_state "deploying" "v1.2.9" "abc1234"
cat "$DEPLOY_STATE"
"""
        result = _run(body, bash_env, ("check_deploy", "write_state"))
        assert result.returncode == 0, result.stderr
        state = json.loads(result.stdout)
        assert state["state"] == "deploying"
        assert state["tag"] == "v1.2.9"
        assert state["sha"] == "abc1234"
        assert state["updated_at"]

    def test_write_state_preserves_waiting_since_on_repeat(self, bash_env):
        body = """
write_state "waiting" "v1.2.9" "abc1234" "status_file_stale"
first=$(python3 -c "import json, os;print(json.load(open(os.environ['DEPLOY_STATE']))['waiting_since'])")
sleep 1
write_state "waiting" "v1.2.9" "abc1234" "status_file_stale"
second=$(python3 -c "import json, os;print(json.load(open(os.environ['DEPLOY_STATE']))['waiting_since'])")
[ -n "$first" ] && [ "$first" = "$second" ]
echo WAITING_SINCE_OK
        """
        result = _run(body, bash_env, ("check_deploy", "write_state"))
        assert result.returncode == 0, result.stderr
        assert "WAITING_SINCE_OK" in result.stdout

    def test_write_state_failure_does_not_kill_caller(self, bash_env):
        body = """
mkdir -p "$DEPLOY_STATE"
write_state "deploying" "v1.2.9" "abc1234"
echo SURVIVED
"""
        result = _run(body, bash_env, ("check_deploy", "write_state"))
        assert result.returncode == 0, result.stderr
        assert "SURVIVED" in result.stdout
        log_text = (Path(bash_env["HARNESS_HOST_DIR"]) / "deploy.log").read_text(encoding="utf-8")
        assert "could not persist deploy state" in log_text

    def test_get_position_count_states(self, bash_env):
        fresh = datetime.now(UTC).isoformat()
        stale = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
        body = f"""
cat > "$STATUS_FILE" <<EOF
{{"status": "running", "updated_at": "{fresh}", "position_count": 0}}
EOF
[ "$(get_position_count)" = "0" ] || exit 10
cat > "$STATUS_FILE" <<EOF
{{"status": "running", "updated_at": "{stale}", "position_count": 0}}
EOF
[ "$(get_position_count)" = "STALE" ] || exit 11
rm -f "$STATUS_FILE"
[ "$(get_position_count)" = "ERROR" ] || exit 12
cat > "$STATUS_FILE" <<EOF
{{"status": "running", "updated_at": "{fresh}", "position_count": "many"}}
EOF
[ "$(get_position_count)" = "ERROR" ] || exit 13
echo POSITIONS_OK
"""
        result = _run(body, bash_env, ("check_deploy", "get_position_count"))
        assert result.returncode == 0, result.stderr
        assert "POSITIONS_OK" in result.stdout


class TestDeployShHelpers:
    def test_update_deploy_state_and_write_version(self, bash_env):
        body = """
update_deploy_state "completed"
write_version "v1.2.9" "abc1234"
cat "$DEPLOY_STATE"
echo "---"
cat "$VERSION_FILE"
"""
        result = _run(
            body,
            bash_env,
            ("deploy", "update_deploy_state"),
            ("deploy", "write_version"),
        )
        assert result.returncode == 0, result.stderr
        state_text, version_text = result.stdout.split("---\n")
        assert json.loads(state_text)["last_result"] == "completed"
        version = json.loads(version_text)
        assert version["tag"] == "v1.2.9"
        assert version["sha"] == "abc1234"


class TestScriptSyntax:
    def test_all_deploy_scripts_pass_bash_n(self):
        for script in sorted(DEPLOY_DIR.glob("*.sh")):
            result = subprocess.run(
                [BASH, "-n", str(script)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"{script.name}: {result.stderr}"
