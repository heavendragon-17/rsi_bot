# Enforcement Guide

## Overview

This project enforces 73+ coding rules through 3 layers:
1. **Local hooks** (pre-commit): Fast checks on every commit (~5s)
2. **CI pipeline** (GitHub Actions): Full validation on every PR
3. **Claude Code hooks** (.claude/settings.json): AI agent enforcement

## Quick Reference

### For Human Developers
- Install: `pip install -r requirements-dev.txt && pre-commit install`
- Run all checks: `pre-commit run --all-files`
- Run arch lint: `python scripts/arch_lint.py`
- Run tests: `pytest tests/ --cov=app`

### For AI Agents (Claude Code)
- Pre-commit hook blocks commits with new violations
- Post-edit hook shows violations in context
- CLAUDE.md contains all rules as mandatory instructions

## Rule Inventory

### Enforcement Matrix

| Rule | arch_lint | Ruff | mypy | bandit | CI | pre-commit |
|------|-----------|------|------|--------|-----|------------|
| Import boundaries | ✅ | | | | ✅ | ✅ |
| File size (400 lines) | ✅ | | | | ✅ | ✅ |
| No magic numbers | ✅ | | | | ✅ | ✅ |
| Fee constants | ✅ | | | | ✅ | ✅ |
| Directory whitelist | ✅ | | | | ✅ | ✅ |
| Core file whitelist | ✅ | | | | ✅ | ✅ |
| Class count per file | ✅ | | | | ✅ | ✅ |
| Duplicate helpers | ✅ | | | | ✅ | ✅ |
| No print() | ✅ | | | | ✅ | ✅ |
| No bare except | ✅ | | | | ✅ | ✅ |
| No unittest.TestCase | ✅ | | | | ✅ | ✅ |
| No stdlib logging | ✅ | | | | ✅ | ✅ |
| snake_case filenames | ✅ | | | | ✅ | ✅ |
| I-prefix interfaces | ✅ | | | | ✅ | ✅ |
| Import sorting | | ✅ | | | ✅ | ✅ |
| Code style | | ✅ | | | ✅ | ✅ |
| Bugbear patterns | | ✅ | | | ✅ | ✅ |
| Type errors | | | ✅ | | ✅ | |
| Security patterns | | | | ✅ | ✅ | |
| Vulnerable deps | | | | | pip-audit | |
| Leaked secrets | | | | | ✅ | ✅ |
| Circular imports | | | | | ✅ | |
| Doc freshness | | | | | reminder | |
| Test coverage | | | | | ✅ | |

### Rules Enforced by Convention Only

These rules cannot be statically checked and rely on code review:
- Decimal in live, float64 in backtest
- All exit orders use reduceOnly=True
- Position amounts are signed (positive=LONG, negative=SHORT)
- Strategy params in frozen dataclass (not config.yaml)
- Stateless strategy pattern (no state on self)
- Event-driven architecture (SignalEvent flow)
- No god classes (subjective threshold)
- DRY principle (requires judgment)

## CI Pipeline

### Jobs (10 total)

| Job | Tool | Blocking | Speed |
|-----|------|----------|-------|
| arch-lint | scripts/arch_lint.py | ✅ Yes | ~2s |
| ruff | ruff check | ✅ Yes | ~3s |
| mypy | mypy app/ | ✅ Yes | ~15s |
| bandit | bandit -r app/ | ✅ Yes | ~10s |
| pip-audit | pip-audit | ✅ Yes | ~8s |
| detect-secrets | detect-secrets audit | ✅ Yes | ~3s |
| circular-imports | python -c import | ✅ Yes | ~5s |
| tests | pytest --cov | ✅ Yes | ~30s |
| doc-freshness | git diff check | ❌ Reminder | ~2s |

### Triggers
- **Pull requests** targeting `mua-tren-the-nang`
- **Pushes** to `mua-tren-the-nang`

### Caching
- pip packages cached between runs
- pre-commit environments cached
- mypy cache stored

## Local Hooks

### pre-commit hooks (~5s total)

| Hook | Tool | What |
|------|------|------|
| ruff | ruff-pre-commit | Lint + auto-fix |
| ruff-format | ruff-pre-commit | Code formatting |
| trailing-whitespace | pre-commit-hooks | Remove trailing whitespace |
| end-of-file-fixer | pre-commit-hooks | Ensure newline at EOF |
| check-yaml | pre-commit-hooks | Validate YAML syntax |
| check-added-large-files | pre-commit-hooks | Block files >500KB |
| check-merge-conflict | pre-commit-hooks | Detect merge conflict markers |
| detect-secrets | detect-secrets | Prevent credential commits |
| arch-lint | local | Architecture rule enforcement |

### Claude Code hooks

| Hook | Event | Effect |
|------|-------|--------|
| arch_lint_hook.sh | PreToolUse (git commit) | Blocks commit if violations increase |
| arch_lint_post_edit.sh | PostToolUse (Write/Edit) | Shows violations in agent context |

## Adding New Rules

### To arch_lint.py
1. Add check function following existing pattern
2. Add to `checks` list in `main()`
3. Fix any violations the new rule catches
4. Verify: `python scripts/arch_lint.py` exits 0
5. Update this document's rule inventory

### To Ruff
1. Add rule code to `select` list in `pyproject.toml`
2. Fix violations: `ruff check --fix`
3. Verify: `ruff check app/ tests/ scripts/`

### To CI
1. Add job to `.github/workflows/ci.yml`
2. Add to branch protection required checks
3. Update this document's CI pipeline table

## Coverage Tracking

| Date | Coverage | fail_under | Notes |
|------|----------|------------|-------|
| TBD | TBD% | 0 | Initial measurement |

Target: 70% overall minimum.
Rule: `fail_under` can only increase, never decrease.

## Branch Protection

Settings for `mua-tren-the-nang` branch:
- ✅ Require status checks to pass before merging
- ✅ Require branches to be up to date before merging
- Required checks: arch-lint, ruff, mypy, bandit, pip-audit, detect-secrets, circular-imports, tests
- ❌ Require pull request reviews (not required — CI is the gate)
- ❌ Require signed commits (not required)

### Setup Instructions
1. Go to GitHub → Settings → Branches → Branch protection rules
2. Add rule for `mua-tren-the-nang`
3. Enable "Require status checks to pass"
4. Search and add each required check by name
5. Enable "Require branches to be up to date"
6. Save
