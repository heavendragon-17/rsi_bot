# BTC AI pipeline campaign campaign_c2a7cbdad7b24288

Status: `FAILED`

Jobs: 1; attempts: 2; results: 0
Verification modes: `none`

The checker evidence is authoritative; model prose is not proof.

Live model verified: `True`
Provider model identity verified: `False`
Next missing capability: Complete a live thinker/executor/checker/review loop

Reproduction:

- `python btc_ai_pipeline.py preflight`
- `python btc_ai_pipeline.py run --offline-fixture --fixture-case stop`
- `python btc_ai_pipeline.py run --offline-fixture --use-saved-data --fixture-case stop`
- `python btc_ai_pipeline.py run --live --confirm-live --thinker-provider codex --executor-provider codex --thinker-model <model> --executor-model <model>`
- `python btc_ai_pipeline.py run --live --confirm-live --thinker-provider codex --executor-provider opencode --thinker-model <model> --executor-model opencode-go/muse-spark-1.3-contributor`
