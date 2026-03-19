# CI/CD Pipeline & Code Quality — Full Specification

**Date:** 2026-03-17
**Branch:** `claude/refactor-cicd-prep-NiFf9`
**Scope:** Add GitHub Actions CI/CD, code quality tooling (ruff, mypy, ESLint, Prettier), pre-commit hooks, systemd deployment to VPS, and file size conventions. No structural refactoring of existing code.

---

## 1. Problem Statement

The codebase has:
- **No CI/CD pipeline** — no automated testing, linting, or deployment
- **No code quality tooling** — no linter, formatter, or type checker configured
- **Manual deployment** — bot runs in screen/tmux on VPS, deployed by SSH + manual commands
- **No pre-commit hooks** — code style varies across files

**Goal:** Add automated quality gates and deployment without touching existing code structure. Use a baseline-ignore approach so all existing code passes immediately, and only new/modified code must meet quality standards.

---

## 2. Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| CI/CD platform | GitHub Actions | Already using GitHub |
| Python linting/formatting | ruff (E, F, I, N, B, UP rules) | Fast, replaces 5+ tools |
| Python type checking | mypy (relaxed mode) | Catches obvious errors without requiring full annotations |
| TypeScript linting | ESLint + Prettier | Most mature ecosystem, best plugin support |
| Test runner | pytest + coverage report (no gate) | Coverage visible in PRs but doesn't block merge |
| Pre-commit hooks | ruff format + ruff check | Catch issues before they reach CI |
| Deploy trigger | GitHub release tag | Most controlled for production trading bot |
| Deploy method | systemd + SSH (Docker planned for later) | Simple for single bot, migrate to Docker when multi-bot needed |
| VPS secrets | .env stays on VPS, SSH key in GitHub Secrets | API keys never leave the server |
| Bot restart during deploy | Hard restart | 15m timeframe = negligible risk of missing signal in 10-30s gap |
| Rollback strategy | Re-deploy previous release tag | Simple, reliable, tag-based |
| File size convention | Soft 100 lines, hard 150 (new code only) | Pragmatic balance, shadcn/ui excluded |
| Existing violations | Baseline ignore | Zero disruption, only new violations caught |
| File splitting | Deferred | Skip for now, split organically as files are touched |
| Backtest UI deployment | Not deployed | UI is local-only (dev machine) |

---

## 3. GitHub Actions Pipeline

### 3.1 CI Workflow (runs on every push and PR)

**File:** `.github/workflows/ci.yml`

```yaml
name: CI
on:
  push:
    branches: [mua-tren-the-nang]
  pull_request:
    branches: [mua-tren-the-nang]

jobs:
  python-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - name: Ruff format check
        run: ruff format --check .
      - name: Ruff lint
        run: ruff check .
      - name: Mypy type check
        run: mypy app/ --ignore-missing-imports
      - name: Pytest + coverage
        run: pytest tests/ --cov=app --cov-report=xml --cov-report=term-missing -v
      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage.xml

  frontend-quality:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ui
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: ui/package-lock.json
      - run: npm ci
      - name: ESLint
        run: npx eslint src/ --max-warnings 0
      - name: Prettier check
        run: npx prettier --check "src/**/*.{ts,tsx,css}"
      - name: TypeScript check
        run: npx tsc --noEmit
```

### 3.2 Deploy Workflow (runs on release tag)

**File:** `.github/workflows/deploy.yml`

```yaml
name: Deploy
on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    needs: []  # CI runs separately on the branch/PR before merge
    environment: production
    steps:
      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /opt/rsi_bot
            git fetch origin --tags
            git checkout ${{ github.event.release.tag_name }}
            pip install -r requirements.txt
            sudo systemctl restart rsi-bot
            sleep 3
            sudo systemctl is-active rsi-bot
```

### 3.3 Rollback

To rollback: create a new GitHub release pointing to the previous working tag. The deploy workflow runs again with the older tag.

Manual emergency rollback (SSH into VPS):
```bash
cd /opt/rsi_bot
git checkout v1.2.3  # previous known-good tag
pip install -r requirements.txt
sudo systemctl restart rsi-bot
```

---

## 4. Python Tooling

### 4.1 Ruff Configuration

**File:** `pyproject.toml` (new section, or new file)

```toml
[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "F",   # pyflakes
    "I",   # isort (import sorting)
    "N",   # pep8-naming
    "B",   # flake8-bugbear (common bugs)
    "UP",  # pyupgrade (modernize syntax)
]
ignore = []

# Files that exist before this spec are baselined.
# Ruff will auto-generate this on first run.
# See section 4.4 for baseline procedure.

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["N802", "N803"]  # allow non-PEP8 names in tests

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### 4.2 Mypy Configuration

**File:** `pyproject.toml` (additional section)

```toml
[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
warn_return_any = false
warn_unused_configs = true
check_untyped_defs = false       # relaxed: don't require annotations
disallow_untyped_defs = false    # relaxed: don't require annotations
no_implicit_optional = true
```

### 4.3 Dev Dependencies

**File:** `requirements-dev.txt` (new)

```
ruff>=0.8.0
mypy>=1.13.0
pytest>=8.0.0
pytest-cov>=6.0.0
pre-commit>=4.0.0
```

### 4.4 Baseline Procedure

On first setup, generate a baseline so existing code passes:

```bash
# Auto-fix what ruff can fix (formatting, import sorting)
ruff format .
ruff check --fix .

# Remaining unfixable violations get baselined
# Option A: Use ruff's per-file-ignores for specific files
# Option B: Use inline `# noqa` comments (ruff check --add-noqa)
ruff check --add-noqa .
```

**Important:** The auto-fix step (formatting + safe fixes) WILL modify existing files, but these are cosmetic changes (whitespace, import order, quote style). They don't change behavior. This is the one exception to "don't touch existing code." These changes should be in a single commit with message: `style: apply ruff formatting baseline`.

After baseline, all subsequent CI runs start clean.

---

## 5. TypeScript/React Tooling

### 5.1 ESLint Configuration

**File:** `ui/eslint.config.js` (new, flat config format)

```js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react-refresh/only-export-components": "warn",
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/no-explicit-any": "off",  // too many existing `any` types
    },
  },
  {
    ignores: ["dist/", "node_modules/", "src/components/ui/"],  // exclude shadcn/ui
  }
);
```

### 5.2 Prettier Configuration

**File:** `ui/.prettierrc` (new)

```json
{
  "semi": true,
  "singleQuote": false,
  "tabWidth": 2,
  "trailingComma": "all",
  "printWidth": 100
}
```

**File:** `ui/.prettierignore` (new)

```
dist/
node_modules/
src/components/ui/
```

### 5.3 Baseline Procedure

```bash
cd ui
npx prettier --write "src/**/*.{ts,tsx,css}"
npx eslint src/ --fix
```

Same as Python: cosmetic-only changes in a single commit: `style: apply eslint+prettier formatting baseline`.

---

## 6. Pre-Commit Hooks

**File:** `.pre-commit-config.yaml` (new)

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff-format
      - id: ruff
        args: [--fix]
```

**Setup command:**

```bash
pip install pre-commit
pre-commit install
```

**Note:** Frontend hooks (ESLint/Prettier) are NOT in pre-commit to keep commits fast. Frontend quality is enforced in CI only. If this becomes a problem, we can add `lint-staged` + `husky` later.

---

## 7. VPS Systemd Service

### 7.1 Service Unit File

**File:** `deploy/rsi-bot.service` (new, checked into repo)

```ini
[Unit]
Description=RSI Trading Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/rsi_bot
EnvironmentFile=/opt/rsi_bot/.env
ExecStart=/opt/rsi_bot/venv/bin/python main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 7.2 VPS Initial Setup (one-time, documented)

```bash
# 1. Create bot user
sudo useradd -m -s /bin/bash botuser

# 2. Clone repo
sudo mkdir -p /opt/rsi_bot
sudo chown botuser:botuser /opt/rsi_bot
sudo -u botuser git clone <repo-url> /opt/rsi_bot

# 3. Create virtualenv
sudo -u botuser python3 -m venv /opt/rsi_bot/venv
sudo -u botuser /opt/rsi_bot/venv/bin/pip install -r /opt/rsi_bot/requirements.txt

# 4. Copy .env (contains API keys — NEVER in repo)
sudo -u botuser cp /path/to/.env /opt/rsi_bot/.env

# 5. Install systemd service
sudo cp /opt/rsi_bot/deploy/rsi-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rsi-bot
sudo systemctl start rsi-bot

# 6. Verify
sudo systemctl status rsi-bot
sudo journalctl -u rsi-bot -f
```

### 7.3 GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `VPS_HOST` | VPS IP address or hostname |
| `VPS_USER` | SSH user with sudo access (or botuser with systemctl permissions) |
| `VPS_SSH_KEY` | Private SSH key for VPS_USER |

### 7.4 Sudoers (allow botuser to restart without password)

```bash
# /etc/sudoers.d/rsi-bot
botuser ALL=(ALL) NOPASSWD: /bin/systemctl restart rsi-bot, /bin/systemctl is-active rsi-bot
```

---

## 8. File Size Convention

### 8.1 Rules

- **Target:** 100 lines per file (soft limit)
- **Maximum:** 150 lines per file (hard limit)
- **Applies to:** All new and modified Python/TypeScript files
- **Excludes:** shadcn/ui components (`ui/src/components/ui/`), test files, generated files
- **Enforcement:** Not automated in CI (advisory only). Enforced during code review.
- **Existing files:** No retroactive splitting. Files are split when they are modified for other reasons.

### 8.2 Counting

- Lines are counted including imports, comments, and blank lines
- A file at 148 lines is acceptable; a file at 152 lines should be split
- When splitting, prefer extracting into a sibling file in the same directory with a clear name

### 8.3 Future: Automated Enforcement

If desired later, add a CI check:

```bash
# Find files over 150 lines (excluding vendor/generated)
find app/ ui/src/ -name "*.py" -o -name "*.ts" -o -name "*.tsx" | \
  grep -v "ui/src/components/ui/" | \
  xargs wc -l | awk '$1 > 150 && !/total/ {print}'
```

---

## 9. Project Structure Changes

### 9.1 New Files

```
.github/
├── workflows/
│   ├── ci.yml                    # CI pipeline (lint, type-check, test)
│   └── deploy.yml                # Deploy on release tag

deploy/
├── rsi-bot.service               # systemd unit file
└── setup-vps.sh                  # One-time VPS setup script (optional)

pyproject.toml                     # ruff + mypy config (new or extended)
requirements-dev.txt               # Dev dependencies (ruff, mypy, pytest-cov, pre-commit)
.pre-commit-config.yaml            # Pre-commit hooks

ui/eslint.config.js                # ESLint flat config
ui/.prettierrc                     # Prettier config
ui/.prettierignore                 # Prettier ignore
```

### 9.2 Modified Files

- `requirements.txt` — no changes (production deps only)
- `pyproject.toml` — add `[tool.ruff]` and `[tool.mypy]` sections
- `ui/package.json` — add ESLint, Prettier, and related plugins to devDependencies

### 9.3 Formatting Baseline Commits

Two commits that touch many files but are cosmetic-only:
1. `style: apply ruff formatting baseline` — Python files
2. `style: apply eslint+prettier formatting baseline` — TypeScript/React files

These commits should be reviewed quickly (formatting only, no logic changes).

---

## 10. Implementation Order

### Phase 1: Python Quality Tooling
1. Create `requirements-dev.txt`
2. Add ruff config to `pyproject.toml`
3. Add mypy config to `pyproject.toml`
4. Run `ruff format .` and `ruff check --fix .` (auto-fix)
5. Run `ruff check --add-noqa .` (baseline remaining violations)
6. Commit: `style: apply ruff formatting baseline`
7. Verify: `ruff check .` and `ruff format --check .` pass

### Phase 2: TypeScript Quality Tooling
8. Add ESLint config (`ui/eslint.config.js`)
9. Add Prettier config (`ui/.prettierrc`, `ui/.prettierignore`)
10. Install dev dependencies: `npm install -D eslint @eslint/js typescript-eslint eslint-plugin-react-hooks eslint-plugin-react-refresh prettier`
11. Run `npx prettier --write "src/**/*.{ts,tsx,css}"`
12. Run `npx eslint src/ --fix`
13. Commit: `style: apply eslint+prettier formatting baseline`
14. Verify: `npx eslint src/` and `npx prettier --check "src/**/*.{ts,tsx,css}"` pass

### Phase 3: Pre-Commit Hooks
15. Create `.pre-commit-config.yaml`
16. Test: `pre-commit run --all-files`
17. Commit: `chore: add pre-commit hooks for ruff`

### Phase 4: CI Pipeline
18. Create `.github/workflows/ci.yml`
19. Push and verify CI passes on GitHub
20. Commit: `ci: add GitHub Actions CI pipeline`

### Phase 5: Deploy Pipeline
21. Create `deploy/rsi-bot.service`
22. Create `.github/workflows/deploy.yml`
23. Document VPS setup steps in `deploy/setup-vps.sh`
24. Commit: `ci: add deploy workflow and systemd service`
25. Set up GitHub Secrets (VPS_HOST, VPS_USER, VPS_SSH_KEY)
26. Create first release tag and test deploy

---

## 11. Graceful Deploy (Future Improvement)

Current: hard restart (acceptable for 15m timeframe).

Future: Add SIGTERM handler to `main.py`:

```python
import signal

def handle_sigterm(signum, frame):
    log.info("SIGTERM received, finishing current candle cycle...")
    runner.request_shutdown()  # finish current analyze() loop, then exit

signal.signal(signal.SIGTERM, handle_sigterm)
```

This allows the bot to complete its current candle processing before shutting down. Deploy script would use `systemctl stop` (sends SIGTERM), wait for exit, then `systemctl start`.

---

## 12. Docker Migration (Future)

When you need multiple bots on the same VPS:

1. Add `docker-compose.yml` with per-bot service definitions
2. Each bot service mounts its own `config.yaml` and `.env`
3. Deploy workflow builds image, pushes to GitHub Container Registry (ghcr.io)
4. VPS pulls new image and restarts via `docker compose up -d`
5. Rollback: `docker compose up -d --force-recreate` with previous image tag

This replaces the systemd approach entirely.

---

## 13. Out of Scope

- File splitting / structural refactoring (deferred, done organically)
- Backtest UI deployment (UI is local-only)
- Docker containerization (planned for multi-bot future)
- Test coverage gates (report only, no minimum threshold)
- Security scanning (SAST/DAST)
- Dependency vulnerability scanning (Dependabot — can add later trivially)
- Staging environment
- Database migrations tooling (Alembic)

---

## 14. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Baseline `# noqa` comments add noise | Low | Run `ruff check --add-noqa` only for unfixable violations. Most issues are auto-fixed. |
| Formatting baseline commit makes git blame noisy | Medium | Use `git blame --ignore-rev` with the formatting commit hash. Add to `.git-blame-ignore-revs`. |
| CI fails on existing tests | High | Run `pytest tests/` locally before CI setup. Fix any broken tests first. |
| Deploy interrupts active trade monitoring | Low | 15m timeframe = ~10-30s gap is negligible. Add SIGTERM handler later. |
| VPS SSH key compromise | High | Use deploy keys (read-only repo access). Rotate keys periodically. |
| ESLint/Prettier conflicts with existing code | Medium | Generous config (allow `any`, ignore shadcn). Auto-fix first, manual fixes only if needed. |

---

## 15. Success Criteria

- [ ] `ruff check .` and `ruff format --check .` pass on all Python code
- [ ] `mypy app/` passes with no errors
- [ ] `npx eslint src/` passes with 0 warnings in `ui/`
- [ ] `npx prettier --check "src/**/*.{ts,tsx,css}"` passes in `ui/`
- [ ] `pytest tests/` passes with coverage report generated
- [ ] GitHub Actions CI runs on every push/PR to `mua-tren-the-nang`
- [ ] Creating a GitHub release deploys to VPS automatically
- [ ] Bot runs as systemd service with auto-restart on crash
- [ ] `pre-commit run --all-files` passes locally
- [ ] `.git-blame-ignore-revs` contains formatting baseline commit hashes

---

*Previous spec (Backtest API & UI Redesign) archived to `docs/archive/SPEC_backtest_redesign.md`.*
