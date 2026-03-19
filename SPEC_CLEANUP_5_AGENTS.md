# SPEC Part 5: Multi-Agent Execution Strategy

> **Related**: [Overview](SPEC_CLEANUP_1_OVERVIEW.md) · [Migration](SPEC_CLEANUP_2_MIGRATION.md) · [Refactors](SPEC_CLEANUP_3_REFACTORS.md) · [Tech Debt](SPEC_CLEANUP_4_TECH_DEBT.md)

This document describes how to use multiple Claude Code agents to execute the cleanup efficiently and safely. The key insight: **structure migration is sequential** (each phase depends on the last), but **internal refactors can be parallelized**.

---

## 1. Team Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (You)                         │
│  Owns: main branch, merge decisions, verification gates      │
│  Tool: Claude Code main session                              │
└──────────┬──────────────┬───────────────┬───────────────────┘
           │              │               │
    ┌──────▼──────┐ ┌────▼─────┐ ┌───────▼───────┐
    │  PHASE 1    │ │  PHASE 2 │ │   PHASE 3     │
    │  Structure  │ │  Refactor│ │   Polish       │
    │  (Sequential│ │  (Parallel│ │   (Parallel   │
    │   agents)   │ │   agents)│ │    agents)     │
    └─────────────┘ └──────────┘ └───────────────┘
```

### Phase 1: Structure Migration (Sequential)
**Why sequential**: Each phase changes import paths that the next phase depends on.

| Step | Agent | Task | Depends On |
|------|-------|------|------------|
| 1.1 | Agent-Structure | Create skeleton + constants.py (Migration Phase 1) | — |
| 1.2 | Agent-Structure | Move core/ overflow → trading/ (Migration Phase 2) | 1.1 |
| 1.3 | Agent-Structure | Move strategies → trading/strategy/ (Migration Phase 3) | 1.2 |
| 1.4 | Agent-Structure | Move execution → trading/exchange/ (Migration Phase 4) | 1.3 |
| 1.5 | Agent-Structure | Move sim → trading/exchange/sim/ (Migration Phase 5) | 1.4 |
| 1.6 | Agent-Structure | Move market_data + utils → data/ (Migration Phase 6) | 1.5 |
| 1.7 | Agent-Structure | Move notification/ (Migration Phase 7) | 1.6 |
| 1.8 | Agent-Structure | Split API routes + deprecate (Migration Phase 8) | 1.7 |

**One agent, one long session.** After each step: run `pytest`, fix failures, commit.

### Phase 2: Internal Refactors (Parallel Agents in Worktrees)
**Why parallel**: These refactors touch different file sets. Use git worktrees for isolation.

| Agent | Task | Files Touched | Worktree Branch |
|-------|------|---------------|-----------------|
| Agent-Portfolio | Refactor 1: PortfolioManager decomposition | `app/trading/portfolio/*` | `refactor/portfolio` |
| Agent-Exchange | Refactor 2: FillSimulator extraction | `app/trading/exchange/fill_simulator.py`, `app/backtest/mock_exchange.py`, `app/trading/exchange/sim/sim_exchange.py` | `refactor/exchange` |
| Agent-Indicators | Refactor 3: Indicator merge + Refactor 6: Strategy utils | `app/data/indicators.py`, `app/trading/strategy/utils/*`, `app/trading/strategy/rsi_*.py` | `refactor/indicators` |
| Agent-Backtest | Refactor 4: Backtest service + Refactor 5: Config cleanup | `app/backtest/service.py`, `app/api/routes/backtest_*.py`, `app/core/constants.py`, `app/core/config.py` | `refactor/backtest` |

**Merge order**: Portfolio → Exchange → Indicators → Backtest (each merge may require conflict resolution).

### Phase 3: Polish (Parallel Agents)
After all refactors are merged:

| Agent | Task |
|-------|------|
| Agent-Docs | Update all `docs/` and `wiki/` file paths, architecture diagrams, CLAUDE.md |
| Agent-Tests | Fill test coverage gaps (M11-M15), verify full suite passes |
| Agent-Types | Auto-generate TypeScript types from Pydantic, update frontend API client |

---

## 2. Agent Prompts

### Agent-Structure (Phase 1)
Use this prompt for the main restructure agent. Run as a single long session.

```
You are restructuring the rsi_bot codebase. Follow SPEC_CLEANUP_2_MIGRATION.md exactly.

Rules:
1. Use `git mv` for all file moves (preserves git history)
2. After each phase (2-8), update ALL imports in the codebase:
   - grep for the old import path
   - replace with new import path
   - update __init__.py files
3. After each phase, run `pytest tests/` — ALL tests must pass before proceeding
4. Commit after each phase with message: "refactor: phase N — [description]"
5. During Phase 1, create app/core/constants.py with centralized constants (H1, H2, M2 from tech debt)
6. During Phase 6, merge indicators.py + crossover_indicators.py into app/data/indicators.py
7. During Phase 7, delete app/services/ after confirming it's empty
8. During Phase 8, move deprecated files to deprecated/ with a README.md

Do NOT do internal refactors (Portfolio decomposition, FillSimulator, etc.) — only file moves and import updates.
```

### Agent-Portfolio (Phase 2, Worktree)
```
You are decomposing PortfolioManager. Follow Refactor 1 in SPEC_CLEANUP_3_REFACTORS.md.

Working in: app/trading/portfolio/

Steps:
1. Read the current app/trading/portfolio/manager.py (was app/core/portfolio.py)
2. Extract Position dataclass → models.py
3. Extract _calculate_position_size → position_sizer.py (PositionSizer class)
4. Extract SL/TP logic → sl_tp_manager.py (SLTPManager class)
5. Extract notification calls → notification_dispatch.py (NotificationDispatcher)
6. Create trade_executor.py (TradeExecutor) wiring the components
7. Slim manager.py to facade delegating to components
8. Update all tests: test_portfolio_short.py, test_position_sizing.py, test_soft_sl.py, etc.
9. Run pytest — all portfolio tests must pass
10. Target: no file exceeds 250 lines
```

### Agent-Exchange (Phase 2, Worktree)
```
You are extracting a shared FillSimulator. Follow Refactor 2 in SPEC_CLEANUP_3_REFACTORS.md.

Steps:
1. Analyze shared logic between MockExchange (app/backtest/mock_exchange.py) and SimExchange (app/trading/exchange/sim/sim_exchange.py)
2. Create app/trading/exchange/fill_simulator.py with:
   - FillMode ABC (abstract check_fills method)
   - WickFillMode (candle OHLC based, for backtest)
   - TickFillMode (tick price based, for paper trading)
   - FillSimulator class (shared order matching, position tracking, balance, PnL)
3. Refactor MockExchange to delegate to FillSimulator(WickFillMode())
4. Refactor SimExchange to delegate to FillSimulator(TickFillMode())
5. Run tests: test_mock_exchange_short.py, test_sim_exchange.py, test_sim_tick_scanner.py, test_normalized_orders.py
6. Add type hints (tech debt M4)
7. Target: MockExchange ≤ 350 lines, SimExchange ≤ 250 lines
```

### Agent-Indicators (Phase 2, Worktree)
```
You are merging indicators and creating strategy shared utils. Follow Refactors 3 and 6 in SPEC_CLEANUP_3_REFACTORS.md.

Part A — Indicator Merge:
1. Read app/data/indicators.py (was app/utils/indicators.py)
2. Read the old crossover_indicators.py content (merged during structure phase)
3. Ensure unified Indicators class has both compute_all() and compute_crossover()
4. Verify column names match what each strategy expects
5. Update strategy imports

Part B — Strategy Shared Utils:
1. Create app/trading/strategy/utils/config_helpers.py — extract config merge logic duplicated across strategies
2. Create trade_state.py — extract TradeState serialization
3. Create signal_detection.py — extract crossover detection wrappers
4. Create sl_tp_builders.py — extract SL/TP ladder builders
5. Update all 3 strategies to use shared utils
6. Run tests: test_rsi_momentum.py, test_stateless_strategy.py
```

### Agent-Backtest (Phase 2, Worktree)
```
You are extracting the BacktestService and cleaning up config. Follow Refactors 4 and 5 in SPEC_CLEANUP_3_REFACTORS.md.

Part A — Backtest Service:
1. Create app/backtest/service.py (BacktestService class)
2. Extract business logic from the split route files (backtest_run.py, backtest_results.py, backtest_stream.py)
3. Routes become thin HTTP handlers delegating to BacktestService
4. Run test_api_backtest.py

Part B — Config Cleanup:
1. Ensure app/core/constants.py has all magic numbers centralized
2. Remove strategy params from config.yaml
3. Update AppConfig to not expect strategy-specific keys
4. Remove to_legacy_dict() if all consumers use typed config
5. Update test_config.py, test_config_validation.py
```

### Agent-Docs (Phase 3)
```
You are updating documentation to reflect the new codebase structure.

1. Update CLAUDE.md:
   - New directory layout in "Architecture (Quick Reference)"
   - Update all file path references
   - Update import examples
   - Update command examples if any paths changed

2. Update docs/INDEX.md:
   - Update routing table file paths

3. Update docs/02_architecture/:
   - New component diagram
   - Updated data flow with new module paths

4. Update wiki/:
   - getting-started.md — config.yaml changes (strategy params removed)
   - architecture-overview.md — new directory structure
   - backtest-guide.md — any backtest path changes

5. Run: python scripts/gen_db_docs.py (if schema unchanged, verify output is same)

6. Update docs/workflows/adding-a-strategy.md — new file locations for strategies
```

### Agent-Types (Phase 3)
```
You are setting up auto-generation of TypeScript types from Python Pydantic models.

1. Enhance app/api/export_schema.py to:
   - Export OpenAPI schema from FastAPI app
   - Generate TypeScript interfaces from Pydantic models in app/api/schemas.py
   - Output to ui/src/types/generated.ts

2. Add a script: scripts/gen_ts_types.py
   - Runs the FastAPI app schema export
   - Uses datamodel-code-generator or openapi-typescript to generate TS types
   - Overwrites ui/src/types/generated.ts

3. Update ui/src/ to import from generated types where applicable

4. Add to CLAUDE.md commands section:
   python scripts/gen_ts_types.py  # regenerate TypeScript types
```

---

## 3. Execution Timeline

```
Day 1: Phase 1 — Structure Migration
├── Agent-Structure: Phases 1-4 (skeleton, core, strategies, exchange)
├── Verify gate: pytest passes
├── Agent-Structure: Phases 5-8 (sim, data, notification, API)
└── Verify gate: pytest passes, smoke test

Day 2: Phase 2 — Internal Refactors (parallel)
├── Agent-Portfolio: PortfolioManager decomposition     ─┐
├── Agent-Exchange: FillSimulator extraction             ├── parallel
├── Agent-Indicators: Indicator merge + strategy utils   │
└── Agent-Backtest: Backtest service + config cleanup   ─┘
    │
    ├── Merge Agent-Portfolio → main (least conflicts)
    ├── Merge Agent-Indicators → main
    ├── Merge Agent-Exchange → main
    └── Merge Agent-Backtest → main
    │
    └── Verify gate: full pytest + smoke test

Day 3: Phase 3 — Polish (parallel)
├── Agent-Docs: Documentation updates    ─┐
├── Agent-Tests: Test coverage gaps       ├── parallel
└── Agent-Types: TypeScript type gen     ─┘
    │
    └── Final verify: pytest + backtest E2E + bot startup
```

---

## 4. Worktree Setup Commands

```bash
# Create worktrees for Phase 2 parallel agents
git worktree add ../rsi_bot_portfolio refactor/portfolio
git worktree add ../rsi_bot_exchange refactor/exchange
git worktree add ../rsi_bot_indicators refactor/indicators
git worktree add ../rsi_bot_backtest refactor/backtest-service

# After merge, clean up
git worktree remove ../rsi_bot_portfolio
git worktree remove ../rsi_bot_exchange
git worktree remove ../rsi_bot_indicators
git worktree remove ../rsi_bot_backtest
```

---

## 5. Conflict Resolution Strategy

Phase 2 agents work in parallel on different files, but some conflicts are expected:

| Agent A | Agent B | Conflict Area | Resolution |
|---------|---------|---------------|------------|
| Portfolio | Exchange | Both touch `IExchange` calls | Portfolio merges first; Exchange adapts |
| Portfolio | Indicators | Strategy files import from both | Indicators merges second; fix strategy imports |
| Backtest | Exchange | MockExchange refactored by Exchange agent | Exchange merges first; Backtest adapts |
| Backtest | Portfolio | Config changes affect portfolio | Backtest merges last |

**Recommended merge order**: Portfolio → Indicators → Exchange → Backtest

After each merge:
1. `pytest tests/` must pass
2. `python -c "from app.trading.engine import TradingEngine"` must succeed
3. Fix any import conflicts before next merge

---

## 6. Verification Pipeline

After each phase/merge, run this verification suite:

```bash
# 1. All tests pass
pytest tests/ -v

# 2. No circular imports
python -c "
from app.core import interfaces, actions, config, events, exceptions
from app.trading.engine import TradingEngine
from app.trading.strategy.loader import STRATEGY_MAP
from app.trading.exchange.factory import create_exchange
from app.data.store import MarketDataStore
from app.data.indicators import Indicators
from app.notification.telegram_notifier import TelegramNotifier
from app.backtest.engine import BacktestEngine
from app.api.main import app
print('All imports OK')
"

# 3. Smoke test: bot starts in mock mode
timeout 5 python main.py --mode mock 2>&1 | head -20
# Should show startup logs without import errors

# 4. Backtest E2E (after Phase 2)
python app/backtest/backtest.py --data app/backtest/data/BTCUSDT_5m.csv --balance 10000 2>&1 | tail -5
# Should complete without errors
```

---

## 7. Rollback Strategy

If any phase fails catastrophically:

```bash
# Phase 1 (structure): revert to pre-restructure commit
git log --oneline -10  # find the commit before Phase 1
git revert <commit-range>

# Phase 2 (worktrees): just delete the worktree, branch untouched
git worktree remove ../rsi_bot_<name>
git branch -D refactor/<name>

# Phase 3 (polish): revert individual commits
```

Each phase is committed separately, so `git bisect` can pinpoint exactly which step broke something.

---

## 8. Practical Tips for Running Multiple Agents

### With Claude Code CLI
```bash
# Terminal 1: Main orchestrator (you)
claude

# Terminal 2: Agent in worktree (after Phase 1 is complete)
cd ../rsi_bot_portfolio
claude  # give it the Agent-Portfolio prompt

# Terminal 3: Another parallel agent
cd ../rsi_bot_exchange
claude  # give it the Agent-Exchange prompt
```

### With Claude Code Agent Tool
If running within a single Claude Code session, use the `Agent` tool with `isolation: "worktree"` for Phase 2 agents:

```
Agent(
  description="Decompose PortfolioManager",
  prompt="[Agent-Portfolio prompt from above]",
  isolation="worktree"
)
```

This automatically:
- Creates a git worktree
- Runs the agent in isolation
- Returns the worktree path and branch name
- You merge manually when ready

### Key Rules
1. **Never run two agents on the same files** — the merge conflicts aren't worth the time savings
2. **Phase 1 must be fully complete** before launching Phase 2 agents — they need the new directory structure
3. **Merge one at a time** — run tests between each merge
4. **The orchestrator (you) handles merges** — agents just commit to their branches

---

*This completes the 5-part cleanup specification. Start with [Part 1: Overview](SPEC_CLEANUP_1_OVERVIEW.md).*
