# Phase 0 report — foundation

## Summary

Phase 0 was executed on `hardening/phase-0`, based on `origin/security/hardening` at `367d2a7`. No phase 1 security features, product features, performance optimizations, Argon2 migration, RLS, token versioning or MFA were started.

## Changes and evidence

| Task | Files/commits | Verification | Result |
|---|---|---|---|
| Repository hygiene and governance | `64d4e68`; `LICENSE`, `SECURITY.md`, `PROGRESS.md`, `CHANGELOG.md`, `docs/`, archived reports | `git diff --check`; repository grep | Done locally |
| Central settings and probes | `181cd24`; `backend/app/core/config.py`, `main.py`, `.env.example` | `python3 -m py_compile backend/app/main.py`; pytest | Done locally |
| Explicit migrations | `2348664`, `e6d362f`; `001_initial.py`, migration test | `alembic upgrade`, `downgrade base`, `upgrade head` on fresh SQLite; `alembic check` on fresh SQLite | Passed on SQLite; PostgreSQL still required |
| CI gates | local backup commit `321583b`; workflow file excluded from published branch | GitHub rejected workflow update due App permission | Blocked for publication |
| Baseline and health tests | `dd41dd3`; tests and `docs/performance.md` | Original baseline: `pytest -q backend`: 5 passed, 1 skipped; frontend `npm run build` passed | Local smoke/build baseline done |
| Phase 0-B security fixes | `7d8f279`; settings, limiter and security tests | Latest local `pytest -q backend`: 7 passed, 3 skipped | Redis-backed tests remain pending on CI |

All commit IDs in this table were checked with `git cat-file -t` and resolve to commit objects. The
earlier IDs from the pre-rewrite local history are intentionally not used as evidence for the
published branch.

## Imported foundation from `security/hardening` (not reviewed in Phase 0)

This branch is based on `origin/security/hardening` at `367d2a7` and therefore includes previously
imported security work. That imported baseline includes refresh-token rotation and logout/reuse
detection, login limiting, registration/password hardening, security headers and HSTS, CORS
controls, Mongo authentication configuration, and the common-passwords list. These changes were
not independently reviewed as part of Phase 0; their endpoint-by-endpoint review belongs to the
next security review gate and must not be treated as Phase 0 evidence.

## Phase 0-B fixes and evidence

- Registration now checks and records the per-IP registration attempt in the same request path;
  the sixth attempt is expected to return `429` with `Retry-After`. The Redis-backed endpoint test
  is in `backend/tests/test_security_hardening.py` and is skipped locally when Redis is unreachable.
- Limiter writes use a Redis transaction containing `INCR` and `EXPIRE`, preventing a successful
  increment from leaving a key without a TTL. The test asserts a positive TTL on the written key.
- Login limiter keys use HMAC-SHA256 digests derived from the configured JWT secret; raw email and
  IP values are not stored in key names. The test asserts both values are absent from the key.
- Runtime configuration in `main.py` now comes from `Settings`; `DOCS_ENABLED` controls the docs,
  ReDoc and OpenAPI URLs, and production validation rejects unsafe documentation, origins,
  registration, or invitation-token settings.
- `dashboard/public/manus-routes.json` and its TODO reference were removed in separate commit
  `ee68219`.

## Commands actually run

- Original Phase 0 run: `pytest -q backend`: **5 passed, 1 skipped**. The skipped test required `TEST_DATABASE_URL`.
- Latest Phase 0-B local run: `pytest -q backend`: **7 passed, 3 skipped**. Two skips require a reachable Redis service; one requires `TEST_DATABASE_URL`.
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
- `dashboard/public/manus-routes.json` deletion is tracked as a separate Phase 0-B commit because the only repository reference found was the dashboard TODO entry.

## Remaining risks

The current single-file backend remains harder to maintain than the target modular monolith. PostgreSQL-specific locking and migration behavior still needs CI evidence. The existing Docker images use tags rather than verified digests. Production readiness also requires the approved backups, monitoring, legal review, platform-admin TOTP and measured load test.

## Next gate

Phase 0 is **not presented as fully complete** until PostgreSQL/Redis CI passes and the modular extraction decision is either completed with evidence or explicitly accepted as a separate foundation sub-phase. No phase 1 work should begin before written approval of this report and the remaining blockers.
