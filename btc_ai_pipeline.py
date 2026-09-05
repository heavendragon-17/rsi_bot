"""Repository-root CLI for the bounded BTC AI research pipeline MVP."""

from __future__ import annotations

import argparse
import json
import sys
from app.research_pipeline.contracts import PipelineConfig
from app.research_pipeline.controller import PipelineController, preflight


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default="research/results/btc_ai_pipeline_mvp/pipeline.sqlite")
    parser.add_argument("--output-dir", default="research/results/btc_ai_pipeline_mvp")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--data-dir", default="research/data/btc_four_year_20220828_20260828")
    parser.add_argument("--baseline-packet", default=None)
    parser.add_argument("--horizon-packet", default=None)
    parser.add_argument("--thinker-provider", default="fixture", choices=["fixture", "codex", "opencode"])
    parser.add_argument("--thinker-model", default="fixture-thinker")
    parser.add_argument("--thinker-effort", default="medium")
    parser.add_argument("--executor-provider", default="fixture", choices=["fixture", "codex", "opencode"])
    parser.add_argument("--executor-model", default="fixture-executor")
    parser.add_argument("--executor-effort", default="minimal")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--context-budget", type=int, default=6000)
    parser.add_argument("--output-budget", type=int, default=2000)
    parser.add_argument("--max-thinker-calls", type=int, default=2)
    parser.add_argument("--max-executor-calls", type=int, default=1)
    parser.add_argument("--max-jobs", type=int, default=1)


def _config(args: argparse.Namespace) -> PipelineConfig:
    live = getattr(args, "live", False)
    use_saved_data = getattr(args, "use_saved_data", False)
    verification_mode = "real" if live or use_saved_data else "fixture"
    return PipelineConfig(db_path=args.db, output_dir=args.output_dir, repo_root=args.repo_root, data_dir=args.data_dir, baseline_packet=args.baseline_packet, horizon_packet=args.horizon_packet, thinker_provider=args.thinker_provider, thinker_model=args.thinker_model, thinker_effort=args.thinker_effort, executor_provider=args.executor_provider, executor_model=args.executor_model, executor_effort=args.executor_effort, timeout_seconds=args.timeout_seconds, context_budget=args.context_budget, output_budget=args.output_budget, max_thinker_calls=args.max_thinker_calls, max_executor_calls=args.max_executor_calls, max_jobs=args.max_jobs, verification_mode=verification_mode, live_opt_in=live)


def _print(value: object) -> int:
    sys.stdout.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight_parser = subparsers.add_parser("preflight", help="inspect local setup without calling a model")
    _common(preflight_parser)
    run_parser = subparsers.add_parser("run", help="run one bounded campaign")
    _common(run_parser)
    mode = run_parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline-fixture", action="store_true", help="use deterministic stub providers and synthesized fixture data")
    mode.add_argument("--live", action="store_true", help="opt in to configured provider calls")
    run_parser.add_argument("--confirm-live", action="store_true", help="required acknowledgement for --live")
    run_parser.add_argument("--use-saved-data", action="store_true", help="with --offline-fixture, run stubbed models over the saved BTC raw data")
    run_parser.add_argument("--fixture-case", choices=["stop", "next", "reject", "tamper"], default="stop")
    run_parser.add_argument("--name", default="btc-ai-mvp")
    resume_parser = subparsers.add_parser("resume", help="resume a paused or limit-reached campaign")
    _common(resume_parser)
    resume_parser.add_argument("campaign_id")
    resume_parser.add_argument("--fixture-case", choices=["stop", "next", "reject", "tamper"], default=None)
    resume_parser.add_argument("--reconcile-uncertain", action="store_true", help="explicitly reconcile an uncertain prior provider attempt before resuming")
    status_parser = subparsers.add_parser("status", help="show durable campaign state")
    _common(status_parser)
    status_parser.add_argument("campaign_id")
    args = parser.parse_args(argv)
    if args.command == "preflight":
        return _print(preflight(_config(args)))
    if args.command == "run" and args.live and not args.confirm_live:
        parser.error("--live requires explicit --confirm-live; use --offline-fixture for the no-call demonstration")
    if args.command == "run" and args.offline_fixture and (args.thinker_provider != "fixture" or args.executor_provider != "fixture"):
        parser.error("--offline-fixture only permits fixture providers; use --live --confirm-live for a non-fixture provider")
    if args.command == "run" and args.live and args.thinker_provider == "fixture" and args.executor_provider == "fixture":
        parser.error("--live requires at least one configured non-fixture provider")
    if args.command == "run" and args.use_saved_data and not args.offline_fixture:
        parser.error("--use-saved-data is only valid with --offline-fixture")
    if args.command == "run":
        config = _config(args)
        controller = PipelineController(config)
        campaign_id = controller.create_campaign(name=args.name)
        return _print(controller.run(campaign_id, branch=args.fixture_case if args.offline_fixture else None))
    controller = PipelineController(_config(args))
    if args.command == "resume":
        return _print(controller.resume(args.campaign_id, branch=args.fixture_case, reconcile_uncertain=args.reconcile_uncertain))
    return _print(controller.status(args.campaign_id))


if __name__ == "__main__":
    raise SystemExit(main())
