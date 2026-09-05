"""Descriptive comparison and readable reporting without a hindsight score."""

from __future__ import annotations

from typing import Any


def comparison_report(source: dict, diagnostics: dict) -> dict:
    choices = {}
    for policy in ("ai", "scripted"):
        parameters = source[f"{policy}_parameters"]
        choices[policy] = next(row for row in diagnostics["candidates"]
                               if all(row["parameters"][key] == parameters[key] for key in ("horizon_minutes", "grouping")))
    return {
        **choices, "same_horizon": source["ai_parameters"]["horizon_minutes"] == source["scripted_parameters"]["horizon_minutes"],
        "pooled_summary": source["summary_evidence"]["tables"],
        "limitations": [
            "One saved AI choice after exposure to the full historical preview; no untouched holdout or independent discovery.",
            "Pointwise post-selection intervals are descriptive sensitivity, without adjustment for candidate selection or multiple comparisons.",
            "Seven- and 28-day circular blocks are sensitivity settings, not proof that dependence has been fully captured.",
            "Leaving 28-day blocks out measures historical influence; it is not a prospective test.",
            "Nine candidates provide reference coverage, not nine independent trials, an oracle policy or an objective quality ranking.",
            "Gross returns against an overlapping all-bar comparator are descriptive; costs, execution and tradable alpha are not assessed.",
            "Historical and fresh run timings are single observations with uncontrolled load and cache state; missing provider costs remain unknown.",
        ],
        "next_step": "Freeze several unseen decision packets and matched AI/scripted budgets before a prospective evaluation, with blinded diagnostic review and predefined acceptance criteria.",
    }


def _number(value: Any, digits: int = 5) -> str:
    return "undefined" if value is None else f"{value:.{digits}f}"


def _interval(value: list | None) -> str:
    return "undefined" if value is None else f"[{_number(value[0])}, {_number(value[1])}]"


def render_report(report: dict, diagnostics: dict) -> str:
    comparison = report["comparison"]
    resources = report["resources"]
    ai = resources["historical_ai"]
    settings = diagnostics["settings"]
    lines = [
        "# Research selection quality: retrospective pilot", "",
        "**Benefit not established.** This evaluates one saved AI choice against a fixed scripted policy, using zero new model calls.", "",
        f"Both policies selected the same horizon: **{str(comparison['same_horizon']).lower()}**. "
        "A larger cohort gap, narrower interval or smaller number of groups does not establish a better selection policy.", "",
        "## Checked results", "",
        "All gaps and intervals below are percentage points. A contrast is the cohort signal-minus-baseline gap minus the pooled gap. "
        "Intervals are pointwise post-selection sensitivity estimates; they are not significance decisions.", "",
    ]
    for policy, title in (("ai", "Recorded AI choice"), ("scripted", "Independent scripted choice")):
        choice = comparison[policy]
        lines.extend([f"### {title}: {choice['parameters']['horizon_minutes']} minutes / {choice['parameters']['grouping']}", "",
                      "| Cohort | Signals / baseline | Gap | Contrast | Active signal weeks | Largest signal-week share |",
                      "|---|---:|---:|---:|---:|---:|"])
        for row in choice["cohorts"]:
            support = row["support"]["signal"]
            share = support["max_utc_week_share"]
            share_text = "undefined" if share is None else f"{share * 100:.2f}%"
            lines.append(f"| {row['group']} | {row['signal_n']} / {row['baseline_n']} | {_number(row['delta_pp'])} | "
                         f"{_number(row['contrast_pp'])} | {support['active_utc_weeks']} | {share_text} |")
        lines.extend(["", "| Cohort | Block days | Gap interval | Contrast interval | Valid / undefined paired draws |",
                      "|---|---:|---|---|---:|"])
        for row in choice["cohorts"]:
            for bootstrap in row["bootstrap"]:
                lines.append(f"| {row['group']} | {bootstrap['block_days']} | {_interval(bootstrap['delta_ci_pp'])} | "
                             f"{_interval(bootstrap['contrast_ci_pp'])} | {bootstrap['valid_replicates']} / {bootstrap['undefined_replicates']} |")
        lines.extend(["", "| Cohort | Maximum gap change leaving 28 days out | Gap sign changes | Undefined gap cases | Partial calendar year |",
                      "|---|---:|---:|---:|---|"])
        for row in choice["cohorts"]:
            influence = row["influence"]
            lines.append(f"| {row['group']} | {_number(influence['max_abs_delta_change_pp'])} | {influence['delta_sign_changes']} | "
                         f"{influence['undefined_delta_cases']} | {row['support']['partial_calendar_year']} |")
        lines.append("")
    lines.extend([
        "## Resources", "",
        f"The saved AI campaign used **{ai['model_provider_attempts']} provider attempts**, "
        f"{_number(ai['campaign_span_seconds'], 2)} seconds of campaign span and {_number(ai['provider_elapsed_seconds'], 2)} seconds in provider calls. "
        f"Reported tokens: {ai['reported_input_tokens']} input / {ai['reported_output_tokens']} output. "
        f"All attempts have token usage: {ai['all_attempts_have_token_usage']}.", "",
        f"Provider-reported cost: {ai['reported_cost']}; complete cost coverage: {ai['all_attempts_have_cost']}. "
        "This is not a total campaign cost estimate.", "",
        f"The separately executed scripted summary and chosen cohort took **{resources['scripted']['elapsed_seconds']:.2f} seconds**, with zero model calls. "
        "This is a single local observation, not a controlled speed comparison.", "",
        f"The nine-candidate evaluator took {resources['evaluator']['elapsed_seconds']:.2f} seconds, including "
        f"{resources['evaluator']['statistics_seconds']:.2f} seconds for uncertainty and influence calculations. "
        "This evaluator overhead is separate from both policy runs.", "",
        "## Interpretation and next step", "",
        f"The frozen protocol uses {settings['replications']} paired circular draws for block lengths {settings['block_lengths']} "
        f"and seed {settings['seed']}. The common UTC calendar contains {diagnostics['calendar_grid']['days']} days, "
        f"including {diagnostics['calendar_grid']['signal_zero_days']} days with no included signal events.", "",
    ])
    lines.extend(f"- {limitation}" for limitation in comparison["limitations"])
    lines.extend(["", comparison["next_step"], "",
                  "Artifacts: [frozen protocol](protocol.json), [source snapshot](source_snapshot.json), "
                  "[checked catalog](candidate_catalog.json), [all nine candidate statistics](diagnostics.json), [machine report](report.json).", ""])
    return "\n".join(lines)
