"""Campaign evidence and observed runtime reporting."""
from __future__ import annotations

import json
from typing import Any

from .controller_context import ControllerContext
from .measurements import runtime_measurements


class CampaignReporting(ControllerContext):
    def _write_report(self, campaign_id: str) -> None:
        directory = self.output_dir / campaign_id
        directory.mkdir(parents=True, exist_ok=True)
        report = self.store.summary(campaign_id)
        report["scope"] = "offline fixture or explicitly opted-in local provider; no strategy/config changes"
        attempts = report["attempts"]
        real_attempts: list[dict[str, Any]] = []
        for attempt in attempts:
            if attempt["provider"] == "fixture" or attempt["status"] != "COMPLETED":
                continue
            usage = self._read_optional_json_text(attempt.get("usage_json"))
            real_attempts.append({"attempt_id": attempt["id"], "role": attempt["role"], "phase": attempt["phase"], "requested_model": attempt["model"], "reported_model": usage.get("reported_model"), "usage_available": bool((usage.get("provider_usage") or {}).get("usage_available", False)), "provider": attempt["provider"]})
        report["live_model_verified"] = bool(real_attempts)
        report["provider_reporting"] = {
            "live_model_verified": bool(real_attempts),
            "successful_real_provider_attempts": real_attempts,
            "requested_models": {"thinker": self.config.thinker_model, "executor": self.config.executor_model},
            "reported_models": {item["attempt_id"]: item["reported_model"] for item in real_attempts},
            "model_identity_verified": bool(real_attempts) and all(item["reported_model"] == item["requested_model"] for item in real_attempts),
        }
        report["provider_controls"] = {
            "thinker": self._control_summary(self.config.thinker_provider, self.config.thinker_model, self.config.thinker_effort, self.config.opencode_output_mode),
            "executor": self._control_summary(self.config.executor_provider, self.config.executor_model, self.config.executor_effort, self.config.opencode_output_mode),
        }
        report["verification"] = {
            "requested_mode": self.store.context(campaign_id).get("verification_mode"),
            "result_modes": sorted({mode for row in report["results"] if row.get("evidence_json") for mode in [self._read_optional_json_text(row.get("evidence_json")).get("verification_mode")] if mode}),
            "live_model_verified": bool(real_attempts),
        }
        report["measurements"] = runtime_measurements(report)
        report["live_loop_verified"] = report["measurements"]["live_loop_verified"]
        if not report["live_loop_verified"]:
            report["next_missing_capability"] = "Complete a live thinker/executor/checker/review loop"
        elif not report["measurements"]["adaptive_sequence_verified"]:
            report["next_missing_capability"] = "Complete two distinct verified research experiments with an evidence-driven follow-up"
        else:
            report["next_missing_capability"] = "Evaluate research selection quality and measured provider overhead on a fixed task set"
        report["reproduction"] = {
            "preflight": "python btc_ai_pipeline.py preflight",
            "offline_fixture": "python btc_ai_pipeline.py run --offline-fixture --fixture-case stop",
            "offline_saved_data": "python btc_ai_pipeline.py run --offline-fixture --use-saved-data --fixture-case stop",
            "live_opt_in": "python btc_ai_pipeline.py run --live --confirm-live --thinker-provider codex --executor-provider codex --thinker-model <model> --executor-model <model>",
            "live_opencode_executor": "python btc_ai_pipeline.py run --live --confirm-live --thinker-provider codex --executor-provider opencode --thinker-model <model> --executor-model opencode-go/muse-spark-1.3-contributor",
        }
        (directory / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        modes = sorted({mode for row in report["results"] if row.get("evidence_json") for mode in [self._read_optional_json_text(row.get("evidence_json")).get("verification_mode")] if mode})
        lines = [f"# BTC AI pipeline campaign {campaign_id}", "", f"Status: `{report['campaign']['status']}`", "", f"Jobs: {len(report['jobs'])}; attempts: {len(report['attempts'])}; results: {len(report['results'])}", f"Verification modes: `{', '.join(modes) or 'none'}`", "", "The checker evidence is authoritative; model prose is not proof.", "", f"Live model verified: `{report['live_model_verified']}`", f"Provider model identity verified: `{report['provider_reporting']['model_identity_verified']}`", f"Next missing capability: {report['next_missing_capability']}", "", "Reproduction:", "", "- `python btc_ai_pipeline.py preflight`", "- `python btc_ai_pipeline.py run --offline-fixture --fixture-case stop`", "- `python btc_ai_pipeline.py run --offline-fixture --use-saved-data --fixture-case stop`", "- `python btc_ai_pipeline.py run --live --confirm-live --thinker-provider codex --executor-provider codex --thinker-model <model> --executor-model <model>`", "- `python btc_ai_pipeline.py run --live --confirm-live --thinker-provider codex --executor-provider opencode --thinker-model <model> --executor-model opencode-go/muse-spark-1.3-contributor`"]
        (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _read_optional_json_text(value: Any) -> dict[str, Any]:
        if not isinstance(value, str):
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _control_summary(provider: str, model: str, effort: str, output_mode: str = "json_schema") -> dict[str, Any]:
        if provider == "opencode":
            return {
                "provider": provider,
                "model": model,
                "structured_output": {"mode": output_mode, "provider_enforced": output_mode == "json_schema", "local_validation": True},
                "effort": {
                    "requested": effort,
                    "enforced": "request_parameter",
                    "provider_supported": "preflight_or_success_response",
                    "mechanism": "session.prompt.variant",
                },
                "context_budget": {"enforced": "controller_prompt_estimate", "provider_flag": False},
                "output_budget": {"enforced": "controller_response_estimate", "provider_flag": False},
                "timeout": {"enforced": "overall_http_deadline", "provider_supported": True, "owned_process_cleanup": False},
            }
        return {
            "provider": provider,
            "model": model,
            "effort": {"requested": effort, "enforced": provider == "codex", "provider_supported": provider == "codex"},
            "context_budget": {"enforced": "controller_prompt_estimate", "provider_flag": False},
            "output_budget": {"enforced": "controller_response_estimate", "provider_flag": False},
            "timeout": {"enforced": "owned_process_group" if provider == "codex" else False},
        }
