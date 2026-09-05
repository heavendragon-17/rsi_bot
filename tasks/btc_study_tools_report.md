# BTC population study tools implementation report

Scope: bounded task 3 in [the adaptive pipeline plan](btc_adaptive_pipeline_plan.md).

- [x] Add synthetic arithmetic, identity, gap and causal-label regressions first.
- [x] Implement fixed-population summaries and registered cohort comparisons.
- [x] Independently verify saved prices, timestamps, statuses and inclusion flags.
- [x] Verify focused suites and document the integration interface.

## API

`app.research_pipeline.study_tools.prepare_study_context(params: dict, context: ToolContext) -> dict`

Returns `btc-m5-study-context-v1`, with `status: UNVERIFIED`, an explicit saved-preview
description, `alpha_assessment: NOT_ASSESSED`, `horizons_minutes: [60, 120, 180]`,
`available_groupings: [calendar_year, trend, volatility]`, `calendar_years`, `tables`,
`input_identity`, and `limitations`. The preview validates immutable input hashes and
packet structure. Its numbers remain unverified until the full study checker runs.
No full M5 raw-candle scan or artifact write is performed by this preview.

`app.research_pipeline.study_tools.execute_study_tool(task: str, params: dict, context: ToolContext) -> dict`

Registered tasks and model-owned parameters:

- `summarize_m5_horizons`: `mode` (`fixture` or `real`).
- `compare_m5_cohorts`: `mode`, integer `horizon_minutes` (`60`, `120`, `180`), and
  concrete `grouping` (`calendar_year`, `trend`, `volatility`). `choose` is rejected.

Controller injects current `baseline_packet`, `horizon_packet`, `source_csv` (M5),
and `h1_source_csv` paths. Saved manifest absolute paths are provenance only.
Both modes read the supplied packet and raw files; fixture mode does not synthesize
raw candles from saved outcomes. Paths remain inside the existing registered
research result/data boundaries, including validation of packet child paths.

`ToolContext.frozen_inputs` must contain `baseline_manifest_sha256`,
`horizon_manifest_sha256`, `horizon_signals_sha256`, `horizon_baseline_sha256`,
`source_sha256`, and `h1_source_sha256`. Optional frozen `source_path` and
`h1_source_path` are also compared. The horizon manifest must bind parent
`manifest.json` and `signals.csv` hashes in `parent.files_sha256`, and bind current
M5/H1 hashes in `inputs.files`. Byte hashes are strict, without newline normalization.

## Evidence shape

The result has these fields:

- `schema: btc-m5-study-evidence-v1`
- `task`, model-owned `parameters`, `status: VERIFIED | FAILED`
- `verification_mode: fixture_validation | real_local_data`
- `alpha_assessment: NOT_ASSESSED`, `horizons_minutes: [60, 120, 180]`
- `population_rule`, `input_identity`, `checker_sha256`, `limitations`
- `checks`: compact named checks with `passed`; numerical checks also contain
  `checked_rows`, `mismatch_count`, and up to three event/horizon examples.
- `tables`: flat summary rows, empty on any failed check.
- `evidence_id`: deterministic SHA-256 of the preceding evidence fields.
- `unavailable_regime_events`: signal/baseline counts when using regime groupings.

Each table row contains `horizon_minutes`, `grouping`, `group`, and:

| Signal field | Baseline field | Meaning |
|---|---|---|
| `signal_n` | `baseline_n` | Matched all-four-complete observations |
| `signal_total_n` | `baseline_total_n` | Saved observations in the selected cell |
| `signal_complete_n` | `baseline_complete_n` | Complete outcomes at this horizon |
| `signal_mean_return_pct` | `baseline_mean_return_pct` | Matched gross return mean |
| `signal_median_return_pct` | `baseline_median_return_pct` | Matched gross return median |
| `signal_positive_return_share` | `baseline_positive_return_share` | Fraction strictly above zero |

`signal_minus_baseline_pp` is the difference of matched means in percentage points.
Empty cells have null statistics/difference. Summary rows use `grouping: all`,
`group: ALL`. Cohort rows use the selected grouping and deterministic sorted labels.
Saved excursion columns are never reported because this checker verifies returns.

Artifacts: `context.workspace/artifacts/evidence.json` and `study_tables.csv`.
The controller owns `result_id`, cache identity, and durable persistence and may
rewrite `evidence.json` after attaching its metadata.

Cache fingerprints should include `study_tools.py`, `study_checks.py`,
`research/btc_m5_horizon_diagnostic.py`, `research/btc_m5_regime_review.py`, and
`app/backtest/signal_replay_data.py`, plus tool parameters and frozen input hashes.

## Numerical and population checks

The checker uses independent vectorized raw-candle lookup, not the existing horizon
profile/evaluator. It checks exact trigger and target timestamps/prices, native M5
grid, positive finite closes, intervening gaps, COMPLETE/MISSING_TARGET/GAP/
INCOMPLETE_TAIL statuses, gross return arithmetic, and fixed all-four-complete
eligibility across 60/120/180/240 minutes. The existing metrics helper computes the
compact descriptive summary only after these independent checks pass.

Population checks retain parent M5 IDs, trigger identity and one-hour cooldown;
validate the stored ID hash/count; ensure signals belong to the baseline; and verify
the baseline window, candidate/eligible/exclusion counts against the frozen packet
and raw M5 window. Preparation eligibility itself remains inherited from the parent:
the study tools do not replay the strategy or shared H4 preparation logic.

Trend/volatility reuse existing daily-context and backward-label helpers. Native H1
grid, positive closes and hourly continuity are required. An independent binary
search verifies each joined availability timestamp and label against the last UTC
day available at trigger time. Warmup shortages remain explicit UNAVAILABLE groups.
Raw and packet hashes are rechecked before successful evidence is returned.

## Verification

Initial new tests failed collection because the study module did not exist.
Additional regressions failed for off-grid H1 input and malformed nested manifest
objects before their fixes were implemented.

```powershell
& C:/Users/hkpug/miniconda3/envs/rsi/python.exe -m pytest tests/test_btc_ai_pipeline_studies.py tests/test_btc_m5_horizon_diagnostic.py tests/test_btc_m5_regime_review.py -q -p no:cacheprovider
```

Result: **48 passed in 5.40 seconds**, including 34 new study cases. Cases cover
known arithmetic, tampered prices/returns/timestamps/eligibility, missing horizon
rows, frozen input changes, absent hashes/files, missing targets/intervening bars,
all-four-horizon exclusions, all grouping choices, future H1 invariance, deliberately
incorrect future joins, H1 gaps/off-grid bars, warmup unavailability, mid-analysis
input changes, malformed manifests and path restrictions.

`python -m compileall -q` passed for both new modules. Ruff is unavailable in the
existing `rsi` environment (`No module named ruff`); no dependency was installed.
Module lengths are below the 600-line bound. No full-data/model/network calls,
commits, source packet changes, or changes outside the assigned files were made.

The reusable synthetic fixture helper is
`tests.test_btc_ai_pipeline_studies.build_study_packet(tmp_path)`, returning
`(injected_parameters, ToolContext)` for controller integration tests.

Parent integration still owns registry/contracts/controller/cache changes,
independent review, production-data runs and current product documentation updates.

## Missing comparator materialization follow-up

The committed four-year horizon packet lacks its ignored `baseline.csv`. The new
`app.research_pipeline.study_materialize.materialize_study_packet` API accepts
keyword-only `repo_root`, `horizon_packet`, `baseline_packet`, `data_dir`, and
`workspace` Paths, and returns a dictionary of current `horizon_packet`,
`baseline_packet`, and `data_dir` path strings.

The caller provides a new workspace below `research/results`. The function copies
the historical horizon and parent packets into that workspace under their original
run ID directory names. Parent packet copies may convert CRLF to LF only when that
conversion exactly restores the hash frozen in the horizon manifest. Current raw
source files must already match their expected bytes; they are never normalized or
modified by this function. Existing output directories are rejected.

Reconstruction is allowed only when the frozen comparator records every candidate
as eligible, with zero preparation exclusions. It profiles those exact native M5
bars at four fixed horizons using vectorized exact-target/gap checks and rolling
future extrema. The independent study checker verifies reconstructed arithmetic,
signal identity and fixed populations. All saved baseline metrics, statuses,
counts and exclusions must match the historical summary before output is written.

The derived manifest records original file hashes, source identities, original
comparator facts, parent-copy transformations, reconstructed baseline hash/counts
and materializer code hash. `materialization_report.json` records the independent
checks and every output packet file hash. The original absent CSV's byte identity
is explicitly unknown: this is checked numerical reconstruction, not recovery of
an unrecorded original hash. Alpha remains `NOT_ASSESSED`.

The combined materialization/study/horizon/regime suite passes **58 tests in
11.00 seconds**, including ten new materialization cases. The materializer is
219 lines and compiles cleanly. Tests use synthetic inputs and preserve every
historical fixture/source hash. Source/parent changes, incorrect summaries,
ambiguous eligibility, wrong candidate counts, tampered signals, and output reuse
are rejected. Full saved-data reconstruction is separately authorized by the
parent task; its resulting report is the authoritative run evidence.

The authorized saved-data materialization succeeded in **87.56424 seconds** at
`research/results/btc_adaptive_prepared_20260905`. It reconstructed **420,176 events
and 1,680,704 rows**, checked raw arithmetic and fixed populations, and matched all
four historical baseline summaries. The derived horizon directory is
`run_20260904T084448776441Z_97d3c169`; the derived parent directory is
`run_20260904T084317586748Z_97d3c169`. The source directory remains
`research/data/btc_four_year_20220828_20260828`. No provider/model call occurred.
