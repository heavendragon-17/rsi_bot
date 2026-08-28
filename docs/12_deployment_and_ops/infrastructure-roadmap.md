# Infrastructure Improvement Roadmap

This roadmap is based on a repository, workflow, deployment-script, and live
GitHub-settings audit completed on 2026-08-28. It separates improvements made
in the repository from controls that still require GitHub or VPS changes.

## Completed in the repository

- CI now has least-privilege defaults, immutable action SHAs, concurrency and
  timeouts, exact-ref reusable validation, coverage artifacts, documentation
  link validation, deployment shell syntax validation, and a frontend build.
- Release promotion now accepts exact SemVer tags, proves reachability from the
  default branch, reruns CI on the tag, verifies the SHA, and uses a protected
  force-with-lease update.
- Host deployment now fails closed on missing, stale, stopped, or malformed bot
  status; verifies the tag, SHA, and new process start time; suppresses failed
  candidate restart loops; and attempts a verified rollback.
- The VPS installer provisions a dedicated service user, narrow passwordless
  service-control commands, protected logs, and hardened systemd defaults.
- The container uses Python 3.13, runs as a non-root user, and excludes secrets,
  local state, caches, and development artifacts from its build context.
- Dependabot covers GitHub Actions, Python, npm, and the pinned Docker base
  image.
- Frontend bundles are rebuilt from the npm lockfile in CI and remain outside
  version control.
- Documentation now has an explicit lifecycle, archive, task-based index, and
  deterministic local-link check.

These changes still need a real GitHub Actions run and a staged VPS deployment
after they are pushed. Local validation cannot prove hosted-runner behavior,
GitHub protection rules, exchange connectivity, or systemd rollback behavior.

## Prioritization method

Scores use `(Impact + Risk) × (6 − Effort)`, with each input rated 1–5. Higher
scores should be scheduled first; priority also reflects dependency order.

| Priority | Improvement | I | R | E | Score | Definition of done |
|---|---|---:|---:|---:|---:|---|
| P0 | Protect the default branch and production environment | 5 | 5 | 1 | 50 | PRs required; ten current CI checks required and strict; force-push/deletion blocked on default; production has reviewer and ref policy |
| P0 | Add authentication and network isolation to the FastAPI UI/API | 5 | 5 | 3 | 30 | API binds to loopback/private network by default; authenticated TLS proxy or application auth; write endpoints authorized; security tests added |
| P0 | Move runtime secrets out of long-lived `.env` files | 5 | 5 | 3 | 30 | Managed secret store or encrypted host credentials; least-privilege exchange keys; documented rotation and emergency revoke drill |
| P1 | Lock and split dependencies | 4 | 5 | 3 | 27 | Reproducible Python lock with hashes; runtime/dev/research groups separated; npm lock retained; automated update and rollback process |
| P1 | Add service-level monitoring and paging | 4 | 5 | 3 | 27 | Metrics for data age, reconnects, rejected orders, reconciliation drift, deploy health, and process restarts; alerts have owners and runbooks |
| P1 | Define backup and disaster recovery for durable state | 4 | 4 | 3 | 24 | SQLite/config/audit artifacts classified; encrypted backups; retention and restore test; stated RPO/RTO |
| P1 | Build and deploy an immutable image artifact | 4 | 5 | 4 | 18 | CI builds one signed/SBOM-attested image; staging and production pull the same digest; required UI assets are compiled into the artifact; health result is reported to GitHub |
| P1 | Reduce repeated CI dependency installation | 3 | 3 | 3 | 18 | Locked cache or purpose-built CI image; measured runtime improvement; security jobs remain isolated where useful |
| P2 | Provision the VPS with infrastructure as code | 4 | 4 | 4 | 16 | Versioned user, packages, firewall, systemd, log rotation, directories, and rollback settings; idempotent staging test |
| P2 | Resolve configuration default drift | 3 | 3 | 2 | 24 | Backtest balance, timeframe, leverage, and warmup semantics have one named source or explicit context-specific defaults with tests |
| P2 | Implement or remove `bot.active` | 3 | 3 | 1 | 30 | Field is a tested kill switch or removed through a migration; operator docs no longer need a compatibility warning |
| P2 | Set and enforce a frontend bundle budget | 3 | 2 | 2 | 20 | Heavy chart/PDF paths are lazy-loaded; an agreed compressed-size budget is documented and enforced in CI without regressing behavior |

## Recommended delivery sequence

### 1. Close the control-plane gaps

Configure a ruleset for `mua-tren-the-nang`, require all intended CI jobs, and
add a reviewer/ref restriction to the `production` environment. The current
default branch is unprotected, while the production environment has no
protection rules and permits administrator bypass.

### 2. Establish a staging lane

Provision a small staging host/account with separate, low-privilege exchange
credentials. Exercise the exact tag promotion and host rollback path there,
including deliberately broken startup, stale status, malformed status, open
positions, failed dependency installation, and rollback health failure.

### 3. Make artifacts reproducible

Create locked dependency groups and then build a single container image for
each release tag. Compile any required frontend assets inside that build,
attach an SBOM and provenance, scan it, deploy by digest, and retain the prior
digest for rollback.

### 4. Add operational evidence

Centralize structured logs and add metrics/alerts before increasing live
capital. Start with candle age, exchange/local position divergence, order
rejections, WebSocket reconnect rate, process restart count, and deployment
state. Run a backup restore and rollback game day quarterly.

### 5. Codify the host

After the staging behavior is stable, express the VPS baseline as Ansible,
cloud-init, or another idempotent tool. Keep secrets outside that code and test
the complete rebuild on a disposable host.

## Architecture direction

The target release path should be:

```text
PR -> protected default branch -> signed tag -> exact-ref CI
   -> signed immutable image -> approved production environment
   -> staging health/canary -> production by digest -> monitored rollback
```

Until that target exists, keep the FastAPI service private, treat the host
health file as a local safety signal rather than full observability, and do not
infer a successful live deployment from a green branch-promotion job.
