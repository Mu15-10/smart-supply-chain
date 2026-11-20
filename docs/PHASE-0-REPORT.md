# Phase 0 report — foundation

## Summary

Phase 0 was executed on `hardening/phase-0`, based on `origin/security/hardening` at `367d2a7`. No phase 1 security features, product features, performance optimizations, Argon2 migration, RLS, token versioning or MFA were started.

## Changes and evidence

| Task | Files/commits | Verification | Result |
|---|---|---|---|
| Repository hygiene and governance | `3182975`; `LICENSE`, `SECURITY.md`, `PROGRESS.md`, `CHANGELOG.md`, `docs/`, archived reports | `git diff --check`; repository grep | Done locally |
| Central settings and probes | `9946c30`; `backend/app/core/config.py`, `main.py`, `.env.example` | `python3 -m py_compile backend/app/main.py`; pytest | Done locally |
| Explicit migrations | `9edeacf`, `841254b`; `001_initial.py`, migration test | `alembic upgrade`, `downgrade base`, `upgrade head` on fresh SQLite; `alembic check` on fresh SQLite | Passed on SQLite; PostgreSQL still required |
| CI gates | local backup commit `321583b`; workflow file excluded from published branch | GitHub rejected workflow update due App permission | Blocked for publication |
| Baseline and health tests | `65a9007`; tests and `docs/performance.md` | `pytest -q backend`: 5 passed, 1 skipped; frontend `npm run build` passed | Local smoke/build baseline done |

## Commands actually run

- `pytest -q backend`: **5 passed, 1 skipped**. The skipped test requires `TEST_DATABASE_URL`.
- `python3 -m py_compile backend/app/main.py`: passed.
- Fresh SQLite migration round trip: **upgrade → downgrade base → upgrade** passed.
- Fresh SQLite `alembic check`: **No new upgrade operations detected**.
- `npm ci --prefix dashboard`: passed.
- `npm run build --prefix dashboard`: passed. Vite reported JS gzip `80.83 kB` and CSS gzip `6.21 kB`.
- `git diff --check`: passed.
- Docker-dependent commands: not run because `docker` is not installed in the execution environment.

## Not implemented or not verified

- Full behavior-preserving extraction of `main.py` into all target modules is not complete. The current API remains compatible and the target structure is documented, but the refactor is deliberately left open rather than claimed complete.
- PostgreSQL/Redis integration and concurrency tests were not executed locally because Docker is unavailable. CI configuration exists only in the local backup branch `hardening/phase-0-with-ci`; GitHub rejected its publication due missing `workflows` permission.
- `ruff`, `mypy`, `pip-audit`, Semgrep, gitleaks and Trivy were not available locally; CI invokes them.
- Backend lockfile with hashes and Docker image digest pinning remain open; no unverified versions or digests were added.
- Full structured JSON logging and a complete architectural import-boundary test remain open.
- The `manus-routes.json` files were retained because the project tooling references them; no deletion was performed without a stronger usage decision.

## Remaining risks

The current single-file backend remains harder to maintain than the target modular monolith. PostgreSQL-specific locking and migration behavior still needs CI evidence. The existing Docker images use tags rather than verified digests. Production readiness also requires the approved backups, monitoring, legal review, platform-admin TOTP and measured load test.

## Next gate

Phase 0 is **not presented as fully complete** until PostgreSQL/Redis CI passes and the modular extraction decision is either completed with evidence or explicitly accepted as a separate foundation sub-phase. No phase 1 work should begin before written approval of this report and the remaining blockers.
