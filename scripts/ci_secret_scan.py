"""Run detect-secrets over tracked production files only."""

from __future__ import annotations

import subprocess

_RESEARCH_PREFIXES = (
    "research/",
    "docs/06_quant_research/",
    "app/research_pipeline/",
)
_RESEARCH_FILES = frozenset(
    {
        "app/backtest/btc_research_phase1.py",
        "btc_ai_pipeline.py",
        "btc_research_phase1.py",
        "tests/test_btc_four_year_data.py",
        "tests/test_btc_research_phase1.py",
    }
)
_RESEARCH_TEST_PREFIXES = (
    "tests/test_btc_ai_pipeline",
    "tests/test_btc_m5_",
    "tests/test_btc_m15_",
)
_GENERATED_PREFIXES = (
    "artifacts/core_v2_1/",
    "ui/build/",
)


def is_ci_secret_scan_excluded(path: str) -> bool:
    """Return whether a tracked path is outside the production CI scope."""
    normalized = path.replace("\\", "/")
    if normalized.lower().endswith(".ipynb"):
        return True
    if normalized.startswith(_GENERATED_PREFIXES):
        return True
    if normalized.startswith(_RESEARCH_PREFIXES) or normalized in _RESEARCH_FILES:
        return True
    return normalized.endswith(".py") and normalized.startswith(_RESEARCH_TEST_PREFIXES)


def tracked_production_files() -> list[str]:
    """List tracked files that belong to the production CI boundary."""
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    return [path for path in tracked if not is_ci_secret_scan_excluded(path)]


def main() -> int:
    """Run the pinned detect-secrets pre-commit hook against production files."""
    from detect_secrets.pre_commit_hook import main as detect_secrets_main

    return detect_secrets_main(
        ["--baseline", ".secrets.baseline", *tracked_production_files()]
    )


if __name__ == "__main__":
    raise SystemExit(main())
