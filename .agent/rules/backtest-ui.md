---
trigger: always_on
---

# Backtest UI Implementation Rules

> **MANDATORY:** Read this BEFORE any implementation work on the backtesting UI.

---

## 🔴 CRITICAL: Documentation-First Protocol

Before writing ANY code for the backtest UI, you MUST:

1. **Read Architecture Docs** → `docs/architecture/SYSTEM_OVERVIEW.md`
2. **Read Database Schema** → `docs/DATABASE.md` (existing, CTO-approved)
3. **Read Constraints** → `docs/constraints/SECURITY_RULES.md`
4. **Read Your Phase Docs** → Depending on your role:
   - Backend → `docs/backend/API_CONTRACTS.md`
   - Frontend → `docs/frontend/COMPONENT_MANIFEST.md`
   - Database → `docs/DATABASE.md`

---

## 🛡️ Constraint Enforcement

### Config Editing Safety
| Action | Allowed | File |
|--------|---------|------|
| ❌ Edit `.py` strategy files from UI | NO | Strategy files are READ-ONLY |
| ✅ Write JSON override files | YES | `config/strategy_overrides/*.json` |
| ✅ Edit `config.yaml` | YES | Global settings only |

### File Access Boundaries
| Operation | Allowed Paths |
|-----------|---------------|
| **READ** | `app/backtest/data/*.csv`, `config/*.yaml`, `config/strategy_overrides/*.json` |
| **WRITE** | `config/strategy_overrides/*.json`, `data/backtest.db` |
| **NEVER** | System files, network requests, arbitrary paths |

### Database Rules
- **Location:** `data/backtest.db` (not `rsi_bot/data/`)
- **Precision:** Use `TEXT` for monetary values, `Decimal` in Python
- **Lazy Load:** `run_timeseries` table (BLOB) only on chart click
- **Compression:** `zlib` for equity/drawdown curves

---

## 📁 Key Files Reference

| Purpose | Path | Notes |
|---------|------|-------|
| **Database Schema** | `docs/DATABASE.md` | CTO-approved, use exactly as defined |
| **Prompts Context** | `docs/prompts/01_CONTEXT_BUNDLE.md` | UI requirements from Figma agent |
| **CSS Variables** | `docs/prompts/01_CONTEXT_BUNDLE.md#css-variables` | Theming rules |
| **Existing Backtest** | `app/backtest/engine.py` | Current implementation |
| **Strategies** | `app/strategies/*.py` | DEFAULT_CONFIG definitions |

---

## ⚠️ Common Mistakes to Avoid

1. **DON'T** create new database tables - use `docs/DATABASE.md` schema exactly
2. **DON'T** edit strategy `.py` files from UI - use JSON overrides only
3. **DON'T** fetch `run_timeseries` in list views - lazy load only
4. **DON'T** use `float` for money - use `Decimal` and `TEXT` in SQLite
5. **DON'T** mix local backtest with VPS logic - they're separate projects

---

## ✅ Verification Checklist

Before completing any implementation task, verify:

- [ ] Database operations use `docs/DATABASE.md` schema
- [ ] No direct `.py` file edits from UI
- [ ] Monetary values use `Decimal`/`TEXT`
- [ ] Heavy data (equity curves) is lazy-loaded
- [ ] UI uses CSS variables from theme system
