# Enforcement and Delivery Controls

This guide describes the controls implemented in the repository and the GitHub
controls that still require administrator configuration. It was reconciled
against the repository and GitHub settings on 2026-08-28.

## Control layers

1. **Local checks** — pre-commit file hygiene, lint, type, security,
   architecture, documentation, import, and test checks.
2. **CI** — a read-only GitHub Actions workflow that validates Python,
   frontend, security, coverage, shell syntax, and local Markdown links.
3. **Release and host gates** — an exact SemVer tag is revalidated, promoted
   to `production`, and accepted by the VPS only when positions are clear and
   the candidate becomes healthy.

Claude Code also has advisory architecture hooks in `.claude/settings.json`.
Those hooks help agents, but CI and branch settings are the merge authority.

## Local verification

Install the development tools and hooks:

```bash
python -m pip install -r requirements-dev.txt
pre-commit install
```

Run the same core checks manually:

```bash
pre-commit run --all-files
python scripts/arch_lint.py
python scripts/check_markdown_links.py
bash -n deploy/*.sh
pytest tests/ --cov=app --cov-fail-under=70
cd ui && npm ci && npm run build
```

### Pre-commit hooks

| Area | Checks |
|---|---|
| Python style | Ruff lint with fixes, Ruff format |
| File hygiene | trailing whitespace, final newline, YAML/TOML/JSON syntax, case conflicts, merge markers, files over 500 KB |
| Documentation | repository-local Markdown links |
| Architecture | `scripts/arch_lint.py` |
| Types | mypy over `app/` |
| Security | Bandit and detect-secrets baseline audit |
| Imports | core/data circular-import smoke check |
| Tests | fail-fast pytest suite |

## CI workflow

`.github/workflows/ci.yml` runs on pushes and pull requests for
`mua-tren-the-nang`, manual dispatches, and release workflow calls. A reusable
caller may supply a `ref`; every checkout then validates that exact ref.

| Required job name | Primary validation | Timeout |
|---|---|---:|
| `Architecture Lint` | architecture rules and deployment shell syntax | 5 min |
| `Ruff Lint` | Python lint | 5 min |
| `Tests + Coverage` | dependency consistency, tests, 70% coverage, XML artifact | 15 min |
| `Type Check` | mypy | 10 min |
| `Security Scan` | Bandit | 5 min |
| `Dependency Audit` | pip-audit of runtime requirements | 10 min |
| `Secret Detection` | tracked-file detect-secrets scan against the baseline | 5 min |
| `Circular Import Check` | core/data import smoke test | 10 min |
| `Documentation` | local Markdown links and blocking PR documentation-impact gate | 5 min |
| `Frontend Build` | `npm ci`, high/critical advisory gate, TypeScript check, and Vite build | 10 min |

The workflow uses read-only repository permissions, cancels superseded runs,
pins third-party actions to immutable commit SHAs, disables persisted checkout
credentials, and pins directly installed validation tools. Coverage is written
to the job summary and retained as an artifact for 14 days.

The documentation-impact step blocks a pull request when runtime or delivery
paths change without a docs, wiki, README, security, or changelog update. The
heuristic is intentionally conservative; a maintainer can add a short note to
one of those surfaces when no longer-lived documentation is needed. Broken
local links are also blocking.

## Release workflow

`.github/workflows/deploy.yml` accepts an exact `vMAJOR.MINOR.PATCH` tag. It:

1. resolves the tag to a commit and requires it to be reachable from
   `mua-tren-the-nang`;
2. calls the full CI workflow against that exact tag;
3. enters the GitHub `production` environment;
4. verifies the checked-out SHA; and
5. promotes the commit to `production` with `--force-with-lease`.

Promotion is not proof of a healthy VPS. The host-side scripts perform the
position, restart, version/SHA/start-time, and rollback checks documented in
the [deployment checklist](../12_deployment_and_ops/deployment-checklist.md).

Frontend output is source-derived: `ui/build/` is ignored and CI rebuilds it
from `ui/package-lock.json`. No workflow commits generated assets or requires
write access for that purpose. Packaging the same validated output into an
immutable release image is tracked in the
[infrastructure roadmap](../12_deployment_and_ops/infrastructure-roadmap.md).

## Current GitHub settings and required action

The repository files cannot enforce GitHub settings by themselves. The live
settings verified on 2026-08-28 are:

| Scope | Current state | Required improvement |
|---|---|---|
| Default branch `mua-tren-the-nang` | **Not protected** | Require pull requests, one approval, strict status checks, and block force-push/deletion |
| `production` branch | Protected; eight legacy CI contexts required; strict mode off; force-push allowed | Restrict promotion to the release workflow/ruleset and decide whether the two new jobs must also block promotion |
| `production` environment | No protection rules; administrators may bypass | Add a required reviewer, restrict deployment refs to release tags, and disable bypass where supported |
| Workflow token default | Read-only | Keep read-only; grant write only to the production-promotion job |

Recommended required checks for the default branch are all ten CI job names in
the table above. If `Frontend Build` or `Documentation` is intentionally
excluded from branch protection, document that exception in the branch ruleset
instead of relying on an accidental omission.

## Rule ownership

| Rule type | Source of truth |
|---|---|
| Architecture and repository conventions | `scripts/arch_lint.py` |
| Python lint/format | `pyproject.toml` and `.pre-commit-config.yaml` |
| Type checking | `pyproject.toml` |
| Coverage threshold | `pyproject.toml` and CI (`70`) |
| Security scan policy | `pyproject.toml`, `.secrets.baseline`, and CI |
| Documentation routing | `docs/INDEX.md` |
| Release and host safety | `.github/workflows/deploy.yml` and `deploy/` |

When adding a check, update its source configuration, local hook when
appropriate, CI job, required GitHub status checks, and this guide in the same
change.
