# SPEC Enforce 2: Tool Stack — Ruff + mypy + bandit + pip-audit + detect-secrets + pre-commit

> **Status**: Draft
> **Date**: 2026-03-22
> **Scope**: Standard Python tooling, pre-commit framework, secret detection
> **Related specs**: [Foundation](SPEC_ENFORCE_1_FOUNDATION.md) · [Rules](SPEC_ENFORCE_3_RULES.md) · [Coverage & Docs](SPEC_ENFORCE_4_COVERAGE_DOCS.md)
> **Depends on**: SPEC_ENFORCE_1 (pyproject.toml and basic CI must exist)

---

## 1. Problem Statement

After PR 1 establishes zero arch_lint violations and basic CI, the codebase still lacks:
- **Code formatting/linting**: No ruff, no isort — inconsistent style
- **Type checking**: No mypy — type errors go undetected
- **Security scanning**: No bandit — insecure patterns undetected
- **Dependency auditing**: No pip-audit — vulnerable packages undetected
- **Secret detection**: No detect-secrets — risk of committing API keys
- **Local hooks**: No pre-commit framework — human developers have no local gates

**Goal**: Add all standard tools to both CI (mandatory gate) and local hooks (fast feedback).

---

## 2. Decision Log

| # | Topic | Decision | Rationale |
|---|-------|----------|-----------|
| 1 | Ruff rules | Defaults + isort (I) + bugbear (B) + pyupgrade (UP) | Good coverage without noise |
| 2 | mypy strictness | Gradual (check annotated only) | Avoids forcing annotations on unrelated code |
| 3 | bandit scope | `app/` first, expand later | Avoid noise from test assertions, script subprocess calls |
| 4 | Local hook speed | ~5s target | Fast enough developers won't skip with `--no-verify` |
| 5 | Local vs CI split | Fast checks local (ruff, detect-secrets, arch-lint); slow checks CI-only (mypy, bandit, pip-audit) | Balance speed vs thoroughness |
| 6 | Secret detection | detect-secrets in both pre-commit + CI | Prevent credential leaks |
| 7 | Hook framework | pre-commit (Python standard) | Well-supported, cacheable |

---

## 3. Create `.pre-commit-config.yaml`

Local hooks must complete in ~5 seconds. Only fast checks run locally.

```yaml
repos:
  # ── Ruff (lint + format) ──────────────────────────────────
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  # ── Standard file hygiene ─────────────────────────────────
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: check-merge-conflict

  # ── Secret detection ──────────────────────────────────────
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: [--baseline, .secrets.baseline]

  # ── Architecture lint (local custom hook) ─────────────────
  - repo: local
    hooks:
      - id: arch-lint
        name: Architecture lint
        entry: python scripts/arch_lint.py
        language: system
        pass_filenames: false
        files: ^app/.*\.py$
        stages: [pre-commit]
```

**Not included locally** (too slow for ~5s target):
- mypy (~10-30s on full codebase)
- bandit (~5-15s)
- pip-audit (~5-10s, requires network)

These run in CI only.

---

## 4. Generate `.secrets.baseline`

Run once to establish baseline of known non-secret strings:

```bash
pip install detect-secrets
detect-secrets scan --exclude-files '\.env$' --exclude-files '\.env\.example$' > .secrets.baseline
```

The baseline file is committed. Future scans compare against it.

**Important**: `.env` and `.env.example` are excluded from scanning — they contain placeholder keys by design.

---

## 5. Fix print() Statements

6 files in `app/` use `print()` instead of structlog (rule: structlog only, zero print statements):

| File | Action |
|------|--------|
| `app/backtest/download_data.py` | Replace `print()` with `structlog.get_logger().info()` |
| `app/backtest/download_tick_data.py` | Replace `print()` with `structlog.get_logger().info()` |
| `app/backtest/backtest.py` | Replace `print()` with `structlog.get_logger().info()` |
| `app/backtest/runners/tick_replay.py` | Replace `print()` with `structlog.get_logger().info()` |
| `app/notification/telegram_bot.py` | Replace `print()` with `structlog.get_logger().info()` |
| `app/api/export_schema.py` | Replace `print()` with `structlog.get_logger().info()` |

**Pattern**:
```python
# Before
print(f"Downloaded {count} candles")

# After
import structlog
logger = structlog.get_logger()
logger.info("downloaded candles", count=count)
```

---

## 6. Fix Ruff Findings

Run `ruff check app/ tests/ scripts/ --fix` to auto-fix:
- Import sorting (isort rules)
- Unused imports
- Pyupgrade suggestions (old-style type hints, etc.)

Manual fixes may be needed for:
- Bugbear warnings (mutable default arguments, etc.)
- Any remaining style issues

---

## 7. Expand CI Workflow

Add 3 new jobs to `.github/workflows/ci.yml`:

```yaml
  mypy:
    name: Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt mypy
      - name: Run mypy
        run: mypy app/ --ignore-missing-imports
      - name: Post mypy summary
        if: failure() && github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const { execSync } = require('child_process');
            const output = execSync('mypy app/ --ignore-missing-imports 2>&1 || true').toString();
            const truncated = output.substring(0, 3000);
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `## mypy Type Check Failed\n\n\`\`\`\n${truncated}\n\`\`\``
            });

  bandit:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install bandit[toml]
      - name: Run bandit
        run: bandit -r app/ -c pyproject.toml
      - name: Post bandit summary
        if: failure() && github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const { execSync } = require('child_process');
            const output = execSync('bandit -r app/ -c pyproject.toml 2>&1 || true').toString();
            const truncated = output.substring(0, 3000);
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `## Bandit Security Scan Failed\n\n\`\`\`\n${truncated}\n\`\`\``
            });

  pip-audit:
    name: Dependency Audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install pip-audit
      - name: Run pip-audit
        run: pip-audit -r requirements.txt

  detect-secrets:
    name: Secret Detection
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install detect-secrets
      - name: Audit secrets baseline
        run: detect-secrets audit --report --baseline .secrets.baseline
```

---

## 8. Handle Initial Tool Findings

### 8.1 mypy (Gradual Mode)

With `check_untyped_defs = false` and `disallow_untyped_defs = false`, mypy only checks functions that **already have type annotations**. Expected issues:
- Missing `return` type on annotated functions
- Type mismatches in annotated code
- Incompatible types in assignments

Fix these as they appear. Do NOT add annotations to unannotated code in this PR.

### 8.2 bandit

With `skips = ["B101"]` (assert allowed), expected findings on `app/`:
- `B108`: Hardcoded `/tmp` paths → fix or add to skips
- `B301`/`B403`: Pickle usage → likely not present
- `B602`/`B603`: Subprocess calls → fix or allowlist
- `B105`: Hardcoded password strings → false positives from config keys

Add specific skips to `pyproject.toml` as needed. Goal: clean scan, not suppressed warnings.

### 8.3 pip-audit

May find vulnerabilities in dependencies. Options:
- Upgrade vulnerable packages
- Add to `pip-audit --ignore-vuln` for false positives or no-fix-available

### 8.4 Ruff

Most issues auto-fixable. Expected manual fixes:
- `B006`: Mutable default arguments (`def f(x=[])`)
- `B007`: Unused loop variable
- `UP` rules: Old-style type hints (`Optional[X]` → `X | None` for 3.11)

---

## 9. Verification Checklist

After this PR is complete:

- [ ] `.pre-commit-config.yaml` exists with ruff, detect-secrets, arch-lint hooks
- [ ] `.secrets.baseline` exists (generated, committed)
- [ ] `pre-commit run --all-files` passes
- [ ] No `print()` statements in `app/` (all converted to structlog)
- [ ] `ruff check app/ tests/ scripts/` clean
- [ ] `mypy app/` clean (gradual mode)
- [ ] `bandit -r app/ -c pyproject.toml` clean
- [ ] `pip-audit -r requirements.txt` clean (or documented exceptions)
- [ ] CI workflow has 7 jobs: arch-lint, ruff, tests, mypy, bandit, pip-audit, detect-secrets
- [ ] All CI jobs pass

---

## 10. Files Changed Summary

### New Files (2)
| File | Purpose |
|------|---------|
| `.pre-commit-config.yaml` | Pre-commit framework configuration |
| `.secrets.baseline` | detect-secrets baseline (generated) |

### Modified Files (~9)
| File | Change |
|------|--------|
| `.github/workflows/ci.yml` | Add mypy, bandit, pip-audit, detect-secrets jobs |
| `pyproject.toml` | Refine bandit skips if needed |
| `app/backtest/download_data.py` | print() → structlog |
| `app/backtest/download_tick_data.py` | print() → structlog |
| `app/backtest/backtest.py` | print() → structlog |
| `app/backtest/runners/tick_replay.py` | print() → structlog |
| `app/notification/telegram_bot.py` | print() → structlog |
| `app/api/export_schema.py` | print() → structlog |
| Various app/ files | Ruff auto-fixes (imports, style) |
