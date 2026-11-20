# Project progress

## Current gate

- Phase: `0` — foundation
- Branch: `hardening/phase-0`
- Status: `doing`
- Last verified base: `origin/security/hardening` at `367d2a7`

## Decisions

- Multi-tenant SaaS for distribution and trading companies in Saudi Arabia first.
- Arabic/RTL first; country packs will make currency, tax, locale and timezone configurable.
- Production public registration is disabled; development may enable it.
- MongoDB is planned for removal after the foundation gate; no removal is performed in phase 0.
- Modular monolith with one API and a separate worker is the target architecture.
- MIT license is used as the default for this public repository.

## Phase 0 tasks

- [done] Documentation and repository hygiene
- [done] Explicit Alembic DDL and round-trip migration test (SQLite verified; PostgreSQL pending)
- [done] Central settings and startup validation (initial foundation)
- [blocked] Modular monolith extraction requires a larger behavior-preserving refactor and remains open in phase 0
- [doing] PostgreSQL/Redis integration test path (CI configuration added; local Docker unavailable)
- [doing] Request IDs and health readiness; structured JSON logging remains open
- [blocked] CI workflow prepared locally but not publishable with current GitHub App workflow permission
- [done] Local build baseline; load baseline remains open

## Open decisions

- Production provider and budget remain deployment decisions after measured staging results.
- Password hashing migration, PostgreSQL RLS, token versions and MFA are phase 1+ decisions.
- Retention and PDPL assumptions require legal review before go-live.
