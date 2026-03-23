# SPEC Enforce 3: arch_lint Expansion — 3 Batches of New Rules

> **Status**: Draft
> **Date**: 2026-03-22
> **Scope**: Expand `scripts/arch_lint.py` with ~15 new static rules across 3 batches, add circular import + doc freshness CI checks
> **Related specs**: [Foundation](SPEC_ENFORCE_1_FOUNDATION.md) · [Toolstack](SPEC_ENFORCE_2_TOOLSTACK.md) · [Coverage & Docs](SPEC_ENFORCE_4_COVERAGE_DOCS.md)
> **Depends on**: SPEC_ENFORCE_1 (baseline at zero), SPEC_ENFORCE_2 (tooling in place)

---

## 1. Problem Statement

`scripts/arch_lint.py` currently enforces 7 rule categories. The full rules inventory has ~32 statically-checkable rules not yet automated. Since the refactor is complete, all rules should pass immediately — no "target state" issues.

**Goal**: Add all remaining static rules to arch_lint.py in 3 batches (per interview decision), plus CI-only runtime checks.

**Approach per batch**:
1. Add rules to `scripts/arch_lint.py`
2. Run lint — fix any violations the new rules catch
3. Verify zero violations
4. Commit the batch

---

## 2. Decision Log

| # | Topic | Decision | Rationale |
|---|-------|----------|-----------|
| 1 | Batch strategy | 3 batches, verify each | Incremental, catch issues early |
| 2 | Circular imports | Both CI and local check | Critical for architecture integrity |
| 3 | Doc freshness | PR reminder only (not blocking) | Encourages updates without blocking PRs |
| 4 | unittest.TestCase | Convert to plain pytest | Project convention: pytest only |
| 5 | Side constants | Enforce SIDE_BUY/SIDE_SELL from actions.py | No raw "BUY"/"SELL" strings in logic |

---

## 3. Batch 1: Code Quality Rules

### Rule 8: No print() statements

**What**: `print(` must not appear in `app/**/*.py`
**Why**: structlog is the mandatory logging framework (ADR-005)
**Detection**: Regex scan for `print(` in app/ files
**Allowlist**: None (all print() should be structlog by now — fixed in PR 2)
**Note**: `scripts/` is exempt (CLI tools may use print)

```python
# Add to FORBIDDEN_PATTERNS or new check function
PRINT_PATTERN = re.compile(r'\bprint\s*\(')
# Allowed files: none in app/, scripts/ is not scanned
```

### Rule 9: No bare except

**What**: `except:` without specifying an exception type
**Why**: Catches SystemExit, KeyboardInterrupt — dangerous in a trading bot
**Detection**: Regex `except\s*:` (not followed by a type)
**Current state**: 0 violations (already clean)

```python
BARE_EXCEPT_PATTERN = re.compile(r'\bexcept\s*:')
```

### Rule 10: No unittest.TestCase

**What**: `class X(TestCase)` or `class X(unittest.TestCase)` in test files
**Why**: Project convention is pure pytest (no TestCase subclassing)
**Detection**: Regex on `tests/**/*.py`
**Current state**: 9 test classes across 4 files need conversion
**Scope**: Scan `tests/` directory (not `app/`)

Files to convert:
| File | Classes |
|------|---------|
| `tests/test_soft_sl_noretest.py` | `TestSoftSLNoRetest` |
| `tests/test_rsi_momentum.py` | `TestEntryConditions`, `TestDivergenceDetection`, `TestSLTPCalculation`, `TestExitManagement`, `TestEdgeCases`, `TestSLTPCalculatorStatic` |
| `tests/test_soft_sl.py` | `TestSoftSL` |
| `tests/test_partial_tp_sl.py` | `TestPartialTPSL` |

**Conversion pattern**:
```python
# Before
class TestSoftSL(unittest.TestCase):
    def setUp(self):
        self.config = create_config()

    def test_something(self):
        self.assertEqual(result, expected)
        self.assertTrue(condition)

# After
import pytest

@pytest.fixture
def config():
    return create_config()

def test_something(config):
    assert result == expected
    assert condition
```

### Rule 11: Side constants enforcement

**What**: Raw `"BUY"` or `"SELL"` string literals in logic code
**Why**: Use `SIDE_BUY`/`SIDE_SELL` from `app/core/actions.py` for consistency
**Detection**: Regex for `"BUY"` / `"SELL"` / `'BUY'` / `'SELL'` outside allowed files
**Current state**: 54 occurrences across 17 files
**Complexity**: HIGH — many are legitimate comparisons. Need smart allowlisting.

**Allowlist**:
- `app/core/actions.py` — defines the constants
- `app/core/snapshots.py` — uses in type annotations/defaults
- `app/core/events.py` — uses in type annotations/defaults
- `tests/**/*.py` — test fixtures commonly use raw strings

**Implementation approach**: This rule is **deferred to a future PR** if the codebase has too many legitimate uses. The rule should be added as a **warning** (not blocking) initially, with a TODO to convert all raw strings to constants. The 54 occurrences need case-by-case review.

**Alternative**: Add as a Ruff custom rule or a standalone check script that lists occurrences for manual review, rather than blocking arch_lint.

### Rule 12: No `logging.getLogger()` in app/

**What**: `logging.getLogger()` or `import logging` usage in `app/`
**Why**: Must use `structlog.get_logger()` exclusively (ADR-005)
**Detection**: Regex for `logging.getLogger` or `import logging` in app/ files
**Current state**: `app/trading/exchange/factory.py` uses `import logging` + `logging.getLogger(__name__)` — needs fixing
**Allowlist**: None

```python
LOGGING_PATTERNS = [
    (re.compile(r'\blogging\.getLogger\b'), "Use structlog.get_logger() instead of logging.getLogger()"),
    (re.compile(r'^import logging$', re.MULTILINE), "Use structlog instead of stdlib logging"),
]
```

---

## 4. Batch 2: Architecture Rules

### Rule 13: backtest/ import boundaries

**What**: `app.backtest` may only import from `app.core`, `app.data`, and `app.trading`
**Why**: Backtest shares strategies/models with live but must not import api/ or notification/
**Detection**: Extend `IMPORT_RULES` dict in arch_lint.py

```python
IMPORT_RULES["app.backtest"] = {
    "deny": ["app.api", "app.notification"],
    "reason": "backtest/ may only import from core/, data/, and trading/",
}
```

### Rule 14: notification/ import boundaries

**What**: `app.notification` may only import from `app.core`
**Why**: Notification is a leaf module — it should not depend on trading, data, or backtest
**Detection**: Extend `IMPORT_RULES`

```python
IMPORT_RULES["app.notification"] = {
    "deny": ["app.trading", "app.data", "app.backtest", "app.api"],
    "reason": "notification/ may only import from core/",
}
```

### Rule 15: repository/ import boundaries

**What**: `app.repository` may only import from `app.core`
**Why**: Repository is a leaf module — pure data access
**Detection**: Extend `IMPORT_RULES`

```python
IMPORT_RULES["app.repository"] = {
    "deny": ["app.trading", "app.data", "app.backtest", "app.api", "app.notification"],
    "reason": "repository/ may only import from core/",
}
```

### Rule 16: snake_case file names

**What**: All `.py` files under `app/` must use snake_case names
**Why**: Project convention — no PascalCase or camelCase file names
**Detection**: Regex `^[a-z][a-z0-9_]*\.py$` on file names (not paths)
**Allowlist**: `__init__.py`, `__pycache__`

```python
def check_snake_case_filenames() -> list[str]:
    violations = []
    snake_pattern = re.compile(r'^[a-z_][a-z0-9_]*\.py$')
    for py_file in APP_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file) or py_file.name == "__init__.py":
            continue
        if not snake_pattern.match(py_file.name):
            rel = py_file.relative_to(REPO_ROOT)
            violations.append(f"  {rel}: filename not snake_case")
    return violations
```

### Rule 17: No circular imports (CI check)

**What**: Python imports must not create cycles
**Why**: Circular imports cause `ImportError` at runtime
**Detection**: Runtime check — attempt importing key modules

This runs as a **CI job**, not in arch_lint.py (requires full dependency install):

```yaml
  circular-imports:
    name: Circular Import Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Check circular imports
        run: |
          python -c "
          from app.core import interfaces
          from app.core import actions
          from app.core import config
          from app.core import constants
          from app.core import events
          from app.core import snapshots
          from app.core import context
          from app.core import exceptions
          from app.core import utils
          from app.data import indicators
          from app.data import store
          print('No circular imports detected')
          "
```

---

## 5. Batch 3: Convention Rules

### Rule 18: I-prefix for interface classes

**What**: ABC subclasses in `app/core/` must start with `I` prefix
**Why**: Convention — `IExchange`, `IStrategy`, not `Exchange`, `Strategy`
**Detection**: AST check on `app/core/interfaces.py` — find classes inheriting from ABC, verify name starts with `I`
**Current state**: All interfaces already follow this convention (IDataProvider, IDataStore, IStrategy, IIndicators, IExchange, IPortfolio, INotifier)

```python
def check_interface_prefix() -> list[str]:
    violations = []
    core_dir = APP_DIR / "core"
    for py_file in core_dir.glob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            inherits_abc = any(
                (isinstance(b, ast.Name) and b.id == "ABC") or
                (isinstance(b, ast.Attribute) and b.attr == "ABC")
                for b in node.bases
            )
            if inherits_abc and not node.name.startswith("I"):
                rel = py_file.relative_to(REPO_ROOT)
                violations.append(
                    f"  {rel}: class {node.name} inherits ABC but doesn't start with 'I'"
                )
    return violations
```

### Rule 19: Doc freshness reminder (CI only, non-blocking)

**What**: If `app/` files changed but `docs/` didn't, post a PR comment reminder
**Why**: CLAUDE.md mandates doc updates after code changes
**Detection**: Git diff between PR base and head

```yaml
  doc-freshness:
    name: Doc Freshness Check
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Check doc freshness
        id: check
        run: |
          APP_CHANGED=$(git diff --name-only origin/${{ github.base_ref }}...HEAD -- 'app/' | wc -l)
          DOCS_CHANGED=$(git diff --name-only origin/${{ github.base_ref }}...HEAD -- 'docs/' | wc -l)
          echo "app_changed=$APP_CHANGED" >> $GITHUB_OUTPUT
          echo "docs_changed=$DOCS_CHANGED" >> $GITHUB_OUTPUT
      - name: Post reminder
        if: steps.check.outputs.app_changed > 0 && steps.check.outputs.docs_changed == 0
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `## Documentation Reminder\n\nCode changed in \`app/\` but no documentation was updated.\nPlease review \`docs/INDEX.md\` for the documentation routing table and update relevant docs.\n\n> This is a reminder, not a blocker.`
            });
```

**Important**: This job does NOT have `continue-on-error: false` — it's informational only. It should not be a required status check.

---

## 6. Updated arch_lint.py Structure

After all 3 batches, `scripts/arch_lint.py` will have these checks:

```
Existing Rules (from PR 1):
  1. Import boundaries (core, trading)          — check_import_boundaries()
  2. File size limits (400 lines)               — check_file_sizes()
  3. Forbidden patterns (WARMUP, MAX_CANDLES)   — check_forbidden_patterns()
  3b. Fee magic numbers                         — (in check_forbidden_patterns)
  4. Directory whitelist                        — check_directory_whitelist()
  5. Core file whitelist                        — check_core_file_whitelist()
  6. Class count per file                       — check_class_count()
  7. Duplicate helpers                          — check_duplicate_helpers()

Batch 1 (Code Quality):
  8.  No print() in app/                        — check_no_print()
  9.  No bare except                            — check_no_bare_except()
  10. No unittest.TestCase                      — check_no_test_case()
  12. No stdlib logging in app/                 — check_no_stdlib_logging()

Batch 2 (Architecture):
  13. backtest/ import boundaries               — (extended check_import_boundaries)
  14. notification/ import boundaries            — (extended check_import_boundaries)
  15. repository/ import boundaries              — (extended check_import_boundaries)
  16. snake_case filenames                       — check_snake_case_filenames()

Batch 3 (Conventions):
  18. I-prefix for interfaces                   — check_interface_prefix()
```

**Deferred rules** (not in arch_lint, enforced by convention or future tooling):
- Rule 11: Side constants (`SIDE_BUY`/`SIDE_SELL`) — too many legitimate uses, needs manual review
- Rule 17: Circular imports — runtime check, CI-only
- Rule 19: Doc freshness — CI-only, non-blocking

---

## 7. CI Workflow Additions

Add to `.github/workflows/ci.yml`:

```yaml
  circular-imports:
    name: Circular Import Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Check circular imports
        run: |
          python -c "
          from app.core import interfaces, actions, config, constants, events, snapshots
          from app.data import indicators, store
          print('No circular imports detected')
          "

  doc-freshness:
    name: Doc Freshness Reminder
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    # Non-blocking — not a required status check
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Check and remind
        uses: actions/github-script@v7
        with:
          script: |
            const { execSync } = require('child_process');
            const base = context.payload.pull_request.base.ref;
            const appChanged = execSync(`git diff --name-only origin/${base}...HEAD -- 'app/' | wc -l`).toString().trim();
            const docsChanged = execSync(`git diff --name-only origin/${base}...HEAD -- 'docs/' | wc -l`).toString().trim();
            if (parseInt(appChanged) > 0 && parseInt(docsChanged) === 0) {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: context.issue.number,
                body: '## Documentation Reminder\n\nCode changed in `app/` but no docs updated. See `docs/INDEX.md` for routing.\n\n> Reminder only — not blocking.'
              });
            }
```

---

## 8. Test File Conversions (unittest.TestCase → pytest)

### Conversion checklist:

| unittest Pattern | pytest Equivalent |
|-----------------|-------------------|
| `class TestX(unittest.TestCase):` | Remove class or keep as plain class (no inheritance) |
| `def setUp(self):` | `@pytest.fixture` |
| `self.assertEqual(a, b)` | `assert a == b` |
| `self.assertTrue(x)` | `assert x` |
| `self.assertFalse(x)` | `assert not x` |
| `self.assertIsNone(x)` | `assert x is None` |
| `self.assertIsNotNone(x)` | `assert x is not None` |
| `self.assertIn(a, b)` | `assert a in b` |
| `self.assertRaises(E)` | `with pytest.raises(E):` |
| `self.assertAlmostEqual(a, b)` | `assert a == pytest.approx(b)` |
| `self.assertGreater(a, b)` | `assert a > b` |
| `self.assertLess(a, b)` | `assert a < b` |

### Files to convert:

1. **`tests/test_soft_sl_noretest.py`** — 1 class
2. **`tests/test_rsi_momentum.py`** — 6 classes (largest conversion)
3. **`tests/test_soft_sl.py`** — 1 class
4. **`tests/test_partial_tp_sl.py`** — 1 class

**Important**: `from unittest.mock import MagicMock, patch` is fine — `unittest.mock` is the standard mocking library and is used with pytest. Only `unittest.TestCase` subclassing is prohibited.

---

## 9. Verification Checklist

After all 3 batches:

- [ ] `python scripts/arch_lint.py` exits 0 with all new rules active
- [ ] No `print()` in `app/**/*.py`
- [ ] No bare `except:` anywhere
- [ ] No `unittest.TestCase` in `tests/`
- [ ] No `logging.getLogger` in `app/`
- [ ] backtest/, notification/, repository/ import boundaries respected
- [ ] All filenames in `app/` are snake_case
- [ ] All ABCs in `app/core/` have I-prefix
- [ ] Circular import CI job passes
- [ ] Doc freshness reminder triggers on app/-only PRs
- [ ] `pytest tests/` passes (converted tests work)
- [ ] CI workflow has 9 jobs total

---

## 10. Files Changed Summary

### Modified Files
| File | Change |
|------|--------|
| `scripts/arch_lint.py` | Add ~8 new check functions, extend IMPORT_RULES |
| `.github/workflows/ci.yml` | Add circular-imports + doc-freshness jobs |
| `app/trading/exchange/factory.py` | Replace `import logging` with `import structlog` |
| `tests/test_soft_sl_noretest.py` | Convert from TestCase to pytest |
| `tests/test_rsi_momentum.py` | Convert 6 TestCase classes to pytest |
| `tests/test_soft_sl.py` | Convert from TestCase to pytest |
| `tests/test_partial_tp_sl.py` | Convert from TestCase to pytest |
