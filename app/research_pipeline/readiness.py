"""No-model-call readiness checks for exact campaign inputs and providers."""
from pathlib import Path
from typing import Any

from .contracts import PipelineConfig
from .inputs import DEFAULT_BASELINE, DEFAULT_HORIZON, resolve_inputs, validate_inputs
from .providers import preflight_provider


def preflight(config: PipelineConfig) -> dict[str, Any]:
    repo_root = Path(config.repo_root).resolve()
    try:
        context = resolve_inputs(config)
        validate_inputs(context, repo_root, repo_root, adaptive=config.adaptive)
        if config.adaptive:
            from .inputs import tool_parameters
            from .study_tools import prepare_study_context
            from .tools import ToolContext
            prepare_study_context(tool_parameters(context, {"mode": config.verification_mode}),
                                  ToolContext(repo_root, repo_root, context["evidence_hashes"]))
        input_error = None
    except (OSError, ValueError, RuntimeError) as error:
        input_error = {"kind": type(error).__name__, "message": str(error)}

    def resolve(raw: str | None, fallback: Path) -> Path:
        if not raw:
            return fallback.resolve()
        value = Path(raw).expanduser()
        return (repo_root / value).resolve() if not value.is_absolute() else value.resolve()

    data_path = resolve(config.data_dir, repo_root / "research" / "data" / "btc_four_year_20220828_20260828")
    packets = {"baseline": resolve(config.baseline_packet, repo_root / DEFAULT_BASELINE), "horizon": resolve(config.horizon_packet, repo_root / DEFAULT_HORIZON)}
    required_files = [data_path / filename for filename in ("BTCUSDT_5m.csv", "BTCUSDT_15m.csv", "BTCUSDT_1h.csv", "BTCUSDT_4h.csv")]
    inaccessible: list[str] = []
    for path in required_files:
        try:
            with path.open("rb") as stream:
                stream.read(1)
        except OSError:
            inaccessible.append(str(path))
    return {
        "inputs_ready": input_error is None,
        "input_error": input_error,
        "live_call_performed": False,
        "providers": {
            "thinker": preflight_provider(config.thinker_provider, config.thinker_model, effort=config.thinker_effort, context_budget=config.context_budget, output_budget=config.output_budget, timeout_seconds=config.timeout_seconds, opencode_output_mode=config.opencode_output_mode),
            "executor": preflight_provider(config.executor_provider, config.executor_model, effort=config.executor_effort, context_budget=config.context_budget, output_budget=config.output_budget, timeout_seconds=config.timeout_seconds, opencode_output_mode=config.opencode_output_mode),
        },
        "data": {"path": str(data_path), "exists": data_path.exists(), "readable": data_path.is_dir() and not inaccessible, "inaccessible_files": inaccessible, "note": "dataset may be ACL-restricted in the managed sandbox; no access controls are changed"},
        "evidence": {name: {"path": str(path), "exists": path.is_dir(), "manifest": (path / "manifest.json").is_file()} for name, path in packets.items()},
        "limits": {"max_thinker_calls": config.max_thinker_calls, "max_executor_calls": config.max_executor_calls, "max_jobs": config.max_jobs, "timeout_seconds": config.timeout_seconds, "context_budget": config.context_budget, "output_budget": config.output_budget},
        "verification_mode": config.verification_mode,
        "opencode_output_mode": config.opencode_output_mode,
        "live_opt_in": config.live_opt_in,
        "opencode": "local server and provider catalog are probed without invoking a model",
    }
