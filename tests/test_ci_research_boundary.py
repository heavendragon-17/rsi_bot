"""Regression checks for the production CI/CD research boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.arch_lint import _is_research_path, _runtime_app_python_files
from scripts.ci_secret_scan import is_ci_secret_scan_excluded

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "relative_path",
    [
        "app/research_pipeline/controller.py",
        "app/backtest/btc_research_phase1.py",
        "research/btc_m5_horizon_diagnostic.py",
        "docs/06_quant_research/btc-m5.md",
        "btc_ai_pipeline.py",
        "btc_research_phase1.py",
        "tests/test_btc_ai_pipeline.py",
        "tests/test_btc_ai_pipeline_readiness.py",
        "tests/test_btc_four_year_data.py",
        "tests/test_btc_m5_horizon_diagnostic.py",
        "tests/test_btc_m15_signal_diagnostic.py",
        "tests/test_btc_research_phase1.py",
    ],
)
def test_research_paths_are_outside_the_runtime_architecture_scope(relative_path):
    assert _is_research_path(ROOT / relative_path)
    assert is_ci_secret_scan_excluded(relative_path)


@pytest.mark.parametrize(
    "relative_path",
    [
        "app/api/main.py",
        "app/backtest/signal_replay_bundle.py",
        "tests/test_signal_review_bundle.py",
        "tests/test_btc_rsi_cross_alert_evaluator.py",
    ],
)
def test_runtime_paths_stay_inside_the_production_scope(relative_path):
    assert not _is_research_path(ROOT / relative_path)
    assert not is_ci_secret_scan_excluded(relative_path)


def test_runtime_architecture_scan_omits_research_modules():
    paths = {_path.relative_to(ROOT).as_posix() for _path in _runtime_app_python_files()}
    assert "app/api/main.py" in paths
    assert "app/research_pipeline/controller.py" not in paths
    assert "app/backtest/btc_research_phase1.py" not in paths


def test_research_code_is_excluded_from_the_production_container():
    dockerignore = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {
        "research",
        "app/research_pipeline",
        "app/backtest/btc_research_phase1.py",
        "btc_ai_pipeline.py",
        "btc_research_phase1.py",
        "tests",
    } <= dockerignore


def test_ci_skips_research_only_changes_and_research_test_collection():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow.count("paths-ignore:") == 2
    for marker in (
        '      - "research/**"',
        '      - "app/research_pipeline/**"',
        "--ignore-glob='tests/test_btc_ai_pipeline*.py'",
        "--ignore-glob='tests/test_btc_m5_*.py'",
        "--ignore-glob='tests/test_btc_m15_*.py'",
        "-x app/research_pipeline,app/backtest/btc_research_phase1.py",
        "python scripts/check_markdown_links.py --exclude-research",
        "python scripts/ci_secret_scan.py",
    ):
        assert marker in workflow


@pytest.mark.parametrize(
    "relative_path",
    [
        "ui/build/assets/index-generated.js",
        "artifacts/core_v2_1/generated.json",
        "research/notebook.ipynb",
    ],
)
def test_generated_files_stay_outside_the_ci_secret_scan(relative_path):
    assert is_ci_secret_scan_excluded(relative_path)
