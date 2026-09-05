# OpenCode for the BTC research pipeline on Windows

Use Windows Command Prompt (CMD). The research pipeline communicates with a
local OpenCode HTTP server, while OpenCode owns the executor's authentication.
The Codex thinker retains its existing separate CLI login. No repository
`.env` edit is needed.

On this host, OpenCode 1.18.29 was installed on 2026-09-05 and a hidden server
was started at `127.0.0.1:4096`. The owner completed the private provider login.
A live Codex/OpenCode study passed numerical checking and final review; a
zero-model replay matched its evidence exactly. See the
[live acceptance report](../../research/results/btc_mixed_live_acceptance_20260905/campaign_e7879087ffc941e2/report.json)
and [replay report](../../research/results/btc_mixed_live_acceptance_20260905/campaign_e7879087ffc941e2/baseline_report.json).
The commands below are for reproduction and future restarts.

## Install and connect

The official [Windows installation instructions](https://opencode.ai/docs/)
support the existing Node.js/npm installation:

```cmd
npm install -g opencode-ai
opencode --version
```

If a CMD window opened before installation cannot find the executable, open a
new CMD window or use its full npm wrapper path:

```cmd
"%APPDATA%\npm\opencode.cmd" --version
```

Connect the configured executor provider using the interactive local prompt:

```cmd
"%APPDATA%\npm\opencode.cmd" auth login --provider opencode-go
```

Follow the browser/provider instructions and enter the key only in OpenCode's
local credential prompt. Do not paste credentials into task messages, command
arguments, configuration files in this repository or committed reports.
[OpenCode Go](https://opencode.ai/docs/go/) requires its own subscription and API
key; installing the OpenCode CLI does not subscribe or purchase credits.
The original configured model is `opencode-go/muse-spark-1.3-contributor`, using
the `high` variant. Provider catalog availability and account access must be
checked independently.

To list connected provider names without printing keys:

```cmd
"%APPDATA%\npm\opencode.cmd" auth list
```

## Run the local server

Keep this CMD window running while the pipeline uses OpenCode:

```cmd
cd /d "C:\Users\hkpug\OneDrive\Documents\Github\rsi_bot"
"%APPDATA%\npm\opencode.cmd" serve --hostname 127.0.0.1 --port 4096
```

The [server interface](https://opencode.ai/docs/server/) is bound to the local
computer. The pipeline's default `OPENCODE_SERVER_URL` already points to
`http://127.0.0.1:4096`. If a server is already listening there, use that server;
do not launch a second one on the same port. Stop a server started in CMD with
Ctrl+C. No Windows startup service or scheduled task is installed by this setup.

In a second CMD window, run a preflight that does not invoke any model:

```cmd
cd /d "C:\Users\hkpug\OneDrive\Documents\Github\rsi_bot"
"C:\Users\hkpug\miniconda3\envs\rsi\python.exe" btc_ai_pipeline.py preflight --executor-provider opencode --executor-model opencode-go/muse-spark-1.3-contributor --executor-effort high --opencode-output-mode json_text
```

The exact-input and model/provider readiness fields must pass before a live
campaign. Population studies additionally need `--adaptive` and complete
prepared-packet paths; see the
[research workflow](../06_quant_research/research-workflow.md#adaptive-population-studies).

For Muse Spark 1.3 Contributor, live campaign commands also need
`--opencode-output-mode json_text`. The first live request showed that this
endpoint rejects the forced tool choice used by OpenCode's schema mode. Text
mode still requires a JSON object passing the pipeline's local schema and
proposal checks; it denies model tools and does not silently retry failures.
Existing campaigns restore their saved mode, so a new CLI flag does not change
an old campaign when using `resume`.

## Run the prepared population study from CMD

The prepared four-year packets on this host are ready for the following bounded
two-study command. Run it from the repository with the local server available
and `codex` on PATH. It permits three thinker calls and two executor calls.
Each invocation creates a new campaign in the selected results directory.

```cmd
cd /d "C:\Users\hkpug\OneDrive\Documents\Github\rsi_bot"
set "PATH=C:\Users\hkpug\AppData\Local\OpenAI\Codex\bin\2d468d2a6f48dd72;%PATH%"
"C:\Users\hkpug\miniconda3\envs\rsi\python.exe" btc_ai_pipeline.py run --live --confirm-live --adaptive ^
  --thinker-provider codex --thinker-model gpt-5.6-sol --thinker-effort high ^
  --executor-provider opencode --executor-model opencode-go/muse-spark-1.3-contributor --executor-effort high ^
  --opencode-output-mode json_text ^
  --baseline-packet research/results/btc_adaptive_prepared_20260905/run_20260904T084317586748Z_97d3c169 ^
  --horizon-packet research/results/btc_adaptive_prepared_20260905/run_20260904T084448776441Z_97d3c169 ^
  --data-dir research/data/btc_four_year_20220828_20260828 ^
  --db research/results/my_live_adaptive/pipeline.sqlite --output-dir research/results/my_live_adaptive ^
  --max-thinker-calls 3 --max-executor-calls 2 --max-jobs 2 ^
  --question "Complete a horizon summary and one evidence-dependent cohort comparison, then stop."
```

The command prints the campaign ID and report path. Reports retain the plans,
checks, decisions, actual provider usage and coverage of unavailable fields.

The completed [two-study live report](../../research/results/btc_adaptive_live_final_20260905/campaign_3f13b814a0294bb6/report.json)
shows a horizon summary followed by a 180-minute volatility comparison and final
STOP. Its [zero-model replay](../../research/results/btc_adaptive_live_final_20260905/campaign_3f13b814a0294bb6/baseline_report.json)
matched both studies. This verifies the pipeline on descriptive historical
evidence; it does not establish alpha or executable P&L.
