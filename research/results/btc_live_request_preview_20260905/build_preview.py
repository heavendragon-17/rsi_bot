"""Capture the three request shapes locally with scripted responses only."""

import json
from pathlib import Path

from app.research_pipeline.contracts import PipelineConfig
from app.research_pipeline.controller import PipelineController
from app.research_pipeline.providers import FixtureProvider

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent


class PreviewProvider(FixtureProvider):
    def complete(self, request):
        destination = "Codex CLI using ChatGPT login / gpt-5.6-sol" if request.role == "thinker" else "OpenCode Go / muse-spark-1.3-contributor via local OpenCode server"
        record = {
            "preview_only": True,
            "external_model_calls": 0,
            "note": "Locally generated using fixture responses. Live model wording and campaign/result identifiers will differ under these same contracts.",
            "role": request.role,
            "phase": request.phase,
            "intended_live_destination": destination,
            "prompt": request.prompt,
            "response_schema": request.schema,
        }
        (OUTPUT / f"{request.phase}_request_preview.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return super().complete(request)


def main():
    cfg = PipelineConfig(
        db_path=str(OUTPUT / "preview.sqlite"), output_dir=str(OUTPUT), repo_root=str(ROOT),
        data_dir="research/data/btc_four_year_20220828_20260828",
        baseline_packet="research/results/btc_adaptive_prepared_20260905/run_20260904T084317586748Z_97d3c169",
        horizon_packet="research/results/btc_adaptive_prepared_20260905/run_20260904T084448776441Z_97d3c169",
        verification_mode="real", thinker_provider="fixture", executor_provider="fixture",
        thinker_model="fixture-thinker", executor_model="fixture-executor",
        max_thinker_calls=2, max_executor_calls=1, max_jobs=1,
    )
    controller = PipelineController(cfg, thinkers={"fixture": PreviewProvider("thinker")}, executors={"fixture": PreviewProvider("executor")})
    campaign = controller.create_campaign(name="local-request-preview-only")
    state = controller.run(campaign)
    if state["status"] not in {"STOPPED", "LIMIT_REACHED"} or state["result_count"] != 1:
        raise RuntimeError("Local request preview did not complete its numerical check")
    print(json.dumps({"campaign_id": campaign, "status": state["status"], "external_model_calls": 0, "preview_directory": str(OUTPUT)}))


if __name__ == "__main__":
    main()
