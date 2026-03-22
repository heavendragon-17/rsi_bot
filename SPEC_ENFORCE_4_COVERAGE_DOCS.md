# SPEC Enforce 4: Coverage Gating + Enforcement Docs + Branch Protection

> **Status**: Draft
> **Date**: 2026-03-22
> **Scope**: pytest-cov integration, coverage ratcheting, `docs/16_enforcement/`, branch protection, `requirements-dev.txt`
> **Related specs**: [Foundation](SPEC_ENFORCE_1_FOUNDATION.md) · [Toolstack](SPEC_ENFORCE_2_TOOLSTACK.md) · [Rules](SPEC_ENFORCE_3_RULES.md)
> **Depends on**: SPEC_ENFORCE_1, 2, 3 (all prior enforcement infrastructure)

---

## 1. Problem Statement

After PRs 1-3, the codebase has:
- Zero arch_lint violations with ~15 rules
- Full tool stack (ruff, mypy, bandit, pip-audit, detect-secrets)
- Pre-commit hooks for local enforcement
- CI pipeline with 9 jobs

Still missing:
- **Coverage measurement**: No pytest-cov, no coverage tracking
- **Coverage gating**: No minimum coverage requirement
- **Enforcement documentation**: Rules are scattered across CLAUDE.md, arch_lint.py, and CI config
- **Developer dependencies**: No `requirements-dev.txt` for tooling
- **Branch protection**: CI passes but doesn't block merge (needs GitHub config)

**Goal**: Complete the enforcement infrastructure with coverage, docs, and the final merge gate.

---

## 2. Decision Log

| # | Topic | Decision | Rationale |
|---|-------|----------|-----------|
| 1 | Coverage strategy | Measure first, then ratchet to 70% | Avoid blocking on day-one low coverage |
| 2 | Coverage scope | `app/` only (not tests/, scripts/) | Measure production code coverage |
| 3 | Coverage threshold | Start at 0%, increase after measurement | Realistic ramp-up |
| 4 | Target threshold | 70% overall minimum | Reasonable for a trading bot with heavy integration logic |
| 5 | Enforcement docs location | `docs/16_enforcement/enforcement.md` | Follows existing numbered folder convention |
| 6 | Branch protection | Require CI pass, no human review | Automated gate only |
| 7 | Dev dependencies | Separate `requirements-dev.txt` | Keep production deps lean |

---

## 3. Add Coverage to CI

### 3.1 Update tests job in `.github/workflows/ci.yml`

```yaml
  tests:
    name: Tests + Coverage
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest-cov
      - name: Run tests with coverage
        run: |
          pytest tests/ -v --tb=short \
            --cov=app \
            --cov-report=term-missing \
            --cov-report=xml:coverage.xml \
            --cov-config=pyproject.toml
      - name: Post coverage summary
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const { execSync } = require('child_process');
            // Get coverage summary from terminal output
            const output = execSync(
              'pytest tests/ --cov=app --cov-report=term --cov-config=pyproject.toml -q --no-header 2>&1 || true'
            ).toString();
            // Extract the coverage table (last lines before the total)
            const lines = output.split('\n');
            const coverageLines = lines.filter(l => l.includes('TOTAL') || l.includes('%'));
            const totalLine = lines.find(l => l.includes('TOTAL'));
            const summary = totalLine || 'Coverage data not available';
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `## Test Coverage Report\n\n\`\`\`\n${summary}\n\`\`\`\n\nFull report available in CI artifacts.`
            });
```

### 3.2 Coverage configuration in `pyproject.toml`

Already configured in PR 1:
```toml
[tool.coverage.run]
source = ["app"]
omit = ["app/__pycache__/*"]

[tool.coverage.report]
show_missing = true
fail_under = 0  # ← Start here, ratchet up after measurement
```

### 3.3 Coverage ratchet process

After the first CI run with coverage:

1. **Measure**: Read the `TOTAL` line from coverage report (e.g., `42%`)
2. **Set floor**: Update `pyproject.toml` → `fail_under = 42`
3. **Ratchet**: Each PR that improves coverage → update `fail_under` upward
4. **Target**: Reach `fail_under = 70` over time

**Never lower `fail_under`** — coverage must monotonically increase.

Document the current coverage and ratchet history in `docs/16_enforcement/enforcement.md`.

---

## 4. Create `requirements-dev.txt`

Development dependencies for local enforcement tools:

```
-r requirements.txt

# Linting & formatting
ruff>=0.8.0

# Type checking
mypy>=1.8.0

# Security
bandit[toml]>=1.7.0
detect-secrets>=1.5.0

# Dependency auditing
pip-audit>=2.7.0

# Testing
pytest-cov>=5.0.0

# Hook framework
pre-commit>=3.6.0
```

**Usage**:
```bash
pip install -r requirements-dev.txt
pre-commit install
```

---

## 5. Create `docs/16_enforcement/enforcement.md`

This is the single-source-of-truth document for all enforcement mechanisms.

### Document structure:

```markdown
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
```

---

## 6. Update `docs/INDEX.md`

Add routing entry for the new enforcement folder:

```markdown
| Enforcement rules, CI/CD, hooks | `16_enforcement/` | `enforcement.md` |
```

---

## 7. Update `CLAUDE.md`

Add reference to enforcement docs:

```markdown
## Enforcement

All coding rules are enforced via automated gates. See `docs/16_enforcement/enforcement.md` for the complete enforcement matrix, CI pipeline details, and how to add new rules.
```

---

## 8. Final CI Workflow (Complete)

After all 4 PRs, the CI workflow has this structure:

```yaml
name: CI

on:
  push:
    branches: [mua-tren-the-nang]
  pull_request:
    branches: [mua-tren-the-nang]

jobs:
  arch-lint:
    # python scripts/arch_lint.py — 15 rule categories, zero tolerance
  ruff:
    # ruff check app/ tests/ scripts/ — defaults + isort + bugbear
  mypy:
    # mypy app/ — gradual mode, annotated code only
  bandit:
    # bandit -r app/ — security scan, app/ scope
  pip-audit:
    # pip-audit -r requirements.txt — dependency vulnerabilities
  detect-secrets:
    # detect-secrets audit — credential leak prevention
  circular-imports:
    # python -c "from app.core import ..." — import cycle detection
  tests:
    # pytest --cov=app — all tests + coverage measurement
  doc-freshness:
    # PR reminder if app/ changed without docs/ — non-blocking
```

All jobs run in parallel. Total CI time: ~60-90 seconds (with caching).

---

## 9. Verification Checklist

After this PR is complete:

- [ ] `requirements-dev.txt` exists with all dev dependencies
- [ ] `pytest tests/ --cov=app` runs and reports coverage
- [ ] Coverage threshold set in `pyproject.toml` (initial measurement)
- [ ] `docs/16_enforcement/enforcement.md` exists with complete rule inventory
- [ ] `docs/INDEX.md` has routing entry for `16_enforcement/`
- [ ] `CLAUDE.md` references enforcement docs
- [ ] CI workflow has 10 jobs (9 blocking + 1 reminder)
- [ ] PR comment shows coverage summary
- [ ] All CI jobs pass
- [ ] Branch protection documented (manual GitHub setup)

---

## 10. Files Changed Summary

### New Files (3)
| File | Purpose |
|------|---------|
| `requirements-dev.txt` | Development dependencies |
| `docs/16_enforcement/enforcement.md` | Complete enforcement documentation |
| `docs/16_enforcement/` | New docs folder |

### Modified Files (4)
| File | Change |
|------|--------|
| `.github/workflows/ci.yml` | Add coverage to tests job, finalize all jobs |
| `pyproject.toml` | Set `fail_under` after measurement |
| `docs/INDEX.md` | Add `16_enforcement/` routing entry |
| `CLAUDE.md` | Add enforcement docs reference |

---

## 11. Post-Merge Checklist (Manual Steps)

These require GitHub UI access and cannot be automated in a PR:

1. **Set up branch protection** on `mua-tren-the-nang`:
   - Require status checks: arch-lint, ruff, mypy, bandit, pip-audit, detect-secrets, circular-imports, tests
   - Require branch up to date
   - No required reviewers

2. **Verify first PR after protection**:
   - Create a test PR with a deliberate violation
   - Confirm CI fails and merge is blocked
   - Fix the violation, confirm CI passes and merge is allowed

3. **Set initial coverage floor**:
   - Read coverage from first CI run
   - Update `pyproject.toml` `fail_under` to measured value
   - Commit the update

---

## 12. Rollout Summary (All 4 PRs)

| PR | Spec | Key Deliverables | CI Jobs |
|----|------|------------------|---------|
| 1 | SPEC_ENFORCE_1 | Fix 10 violations, pyproject.toml, basic CI | 3 (arch-lint, ruff, tests) |
| 2 | SPEC_ENFORCE_2 | pre-commit, detect-secrets, print→structlog | 7 (+mypy, bandit, pip-audit, detect-secrets) |
| 3 | SPEC_ENFORCE_3 | 15 new arch_lint rules, TestCase conversion | 9 (+circular-imports, doc-freshness) |
| 4 | SPEC_ENFORCE_4 | Coverage, enforcement docs, branch protection | 10 (tests+coverage) |

**Total enforcement after all 4 PRs**:
- **15 arch_lint rules** (static, both local + CI)
- **6 CI-only checks** (mypy, bandit, pip-audit, detect-secrets, circular-imports, coverage)
- **9 pre-commit hooks** (fast local feedback)
- **2 Claude Code hooks** (AI agent enforcement)
- **1 PR reminder** (doc freshness, non-blocking)
- **Branch protection** (merge gate)
