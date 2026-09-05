# BTC AI pipeline campaign campaign_80433546095a470b

Status: `PAUSED`

Jobs: 1; attempts: 2; results: 0
Verification modes: `none`

The checker evidence is authoritative; model prose is not proof.

Live model verified: `False`
Provider model identity verified: `False`
Next missing capability: OpenCode executor integration

Reproduction:

- `python btc_ai_pipeline.py preflight`
- `python btc_ai_pipeline.py run --offline-fixture --fixture-case stop`
- `python btc_ai_pipeline.py run --offline-fixture --use-saved-data --fixture-case stop`
- `python btc_ai_pipeline.py run --live --confirm-live --thinker-provider codex --executor-provider codex --thinker-model <model> --executor-model <model>`
