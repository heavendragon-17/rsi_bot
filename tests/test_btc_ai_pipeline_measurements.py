"""Pure reporting regressions for provider-specific usage field names."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.research_pipeline.measurements import runtime_measurements


def _summary(*runtimes: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign": {"status": "STOPPED"},
        "results": [],
        "attempts": [
            {"provider": "codex", "status": "COMPLETED",
             "usage_json": json.dumps({"provider_usage": {"runtime": runtime}})}
            for runtime in runtimes
        ],
    }


def test_codex_reasoning_alias_counts_reported_coverage_without_changing_output_totals() -> None:
    summary = _summary(
        {"reasoning_output_tokens": 161, "output_tokens": 200},
        {"reasoning_output_tokens": 98, "output_tokens": 140},
    )

    measurements = runtime_measurements(summary)

    assert measurements["supplemental_token_usage"]["reasoning"] == {"reported_tokens": 259, "attempts": 2}
    assert measurements["reported_output_tokens"] == 340
    assert measurements["supplemental_token_usage"]["total"] == {"reported_tokens": None, "attempts": 0}


def test_codex_cache_write_alias_counts_explicit_zero_as_available() -> None:
    measurements = runtime_measurements(_summary(
        {"cache_write_input_tokens": 0}, {"cache_write_input_tokens": 0},
    ))

    assert measurements["supplemental_token_usage"]["cache_write"] == {"reported_tokens": 0, "attempts": 2}
    assert measurements["reported_input_tokens"] is None
    assert measurements["reported_output_tokens"] is None


def test_canonical_reasoning_and_nested_cache_write_take_precedence_without_double_counting() -> None:
    measurements = runtime_measurements(_summary(
        {"reasoning": 5, "reasoning_output_tokens": 100, "cache": {"write": 7}, "cache_write_input_tokens": 100},
        {"reasoning": 0, "reasoning_output_tokens": 100, "cache": {"write": 0}, "cache_write_input_tokens": 100},
    ))

    assert measurements["supplemental_token_usage"]["reasoning"] == {"reported_tokens": 5, "attempts": 2}
    assert measurements["supplemental_token_usage"]["cache_write"] == {"reported_tokens": 7, "attempts": 2}


@pytest.mark.parametrize("runtime", [
    {},
    {"reasoning_output_tokens": None, "cache_write_input_tokens": None},
    {"reasoning_output_tokens": True, "cache_write_input_tokens": False},
    {"reasoning_output_tokens": "161", "cache_write_input_tokens": "0"},
    {"reasoning": None, "reasoning_output_tokens": 161, "cache": {"write": None}, "cache_write_input_tokens": 0},
])
def test_unavailable_supplemental_usage_stays_null(runtime: dict[str, Any]) -> None:
    measurements = runtime_measurements(_summary(runtime))

    for field in ("reasoning", "cache_write", "total"):
        assert measurements["supplemental_token_usage"][field] == {"reported_tokens": None, "attempts": 0}
