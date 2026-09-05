"""Explicit OpenCode JSON-text contracts remain local and budgeted."""

import json
from dataclasses import replace

import pytest
from test_btc_ai_pipeline import CountingFixtureProvider, real_fixture_layout

from app.research_pipeline.contracts import PipelineConfig, ProviderError
from app.research_pipeline.controller import PipelineController
from app.research_pipeline.controller_utils import _estimate_tokens


def setup_controller(tmp_path, **overrides):
    cfg, _, _ = real_fixture_layout(tmp_path)
    cfg = replace(cfg, thinker_provider="opencode", thinker_model="test-model", live_opt_in=True,
                  opencode_output_mode="json_text", **overrides)
    provider = CountingFixtureProvider(role="thinker")
    return PipelineController(cfg, thinkers={"opencode": provider}), provider


def test_output_mode_is_validated_and_restored_from_persisted_config(tmp_path):
    cfg, _, _ = real_fixture_layout(tmp_path)
    assert cfg.opencode_output_mode == "json_schema"
    with pytest.raises(ValueError, match="opencode_output_mode"):
        replace(cfg, opencode_output_mode="fallback")
    updated = replace(cfg, opencode_output_mode="json_text")
    assert PipelineConfig.from_dict(updated.as_dict()).opencode_output_mode == "json_text"
    legacy = cfg.as_dict()
    legacy.pop("opencode_output_mode")
    assert PipelineConfig.from_dict(legacy).opencode_output_mode == "json_schema"


def test_json_text_schema_is_sent_in_prompt_and_counted_before_dispatch(tmp_path):
    controller, provider = setup_controller(tmp_path)
    campaign = controller.create_campaign()
    controller.run(campaign)
    request = provider.calls[0]
    assert request.metadata["opencode_output_mode"] == "json_text"
    assert json.loads(request.prompt.split("Required JSON schema:\n", 1)[1]) == request.schema
    assert request.metadata["controller_limits"]["context_budget"]["estimated_input_tokens"] == _estimate_tokens(request.prompt)
    stored = json.loads(controller.store.summary(campaign)["attempts"][0]["request_json"])
    assert stored["opencode_output_mode"] == "json_text"


def test_json_text_schema_cannot_bypass_context_budget(tmp_path):
    controller, provider = setup_controller(tmp_path, context_budget=20)
    campaign = controller.create_campaign()
    with pytest.raises(ProviderError, match="context budget"):
        controller._provider_call(campaign, "not-created", role="thinker", phase="proposal", prompt="Small prompt",
                                  schema={"description": "long schema " * 80}, metadata={}, validator=lambda obj: obj)
    assert provider.calls == []
    assert controller.store.budget(campaign)["thinker_calls"] == 0


def test_resume_keeps_persisted_output_mode_over_constructor_drift(tmp_path):
    controller, provider = setup_controller(tmp_path)
    campaign = controller.create_campaign()
    drifted = PipelineController(replace(controller.config, opencode_output_mode="json_schema"), thinkers={"opencode": provider})
    drifted.resume(campaign)
    assert provider.calls[0].metadata["opencode_output_mode"] == "json_text"
