# BTC AI pipeline campaign campaign_3a869ced481f44ab

Status: `FAILED`

Jobs: 1; attempts: 1; results: 0
Verification modes: `none`

The checker evidence is authoritative; model prose is not proof.

Live model verified: `True`
Provider model identity verified: `False`
Next missing capability: OpenCode executor integration

Reproduction:

- `python btc_ai_pipeline.py preflight`
- `python btc_ai_pipeline.py run --offline-fixture --fixture-case stop`
- `python btc_ai_pipeline.py run --offline-fixture --use-saved-data --fixture-case stop`
- `python btc_ai_pipeline.py run --live --confirm-live --thinker-provider codex --executor-provider codex --thinker-model <model> --executor-model <model>`
