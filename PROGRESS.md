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

- [doing] Documentation and repository hygiene
- [todo] Explicit Alembic DDL and round-trip migration test
- [todo] Central settings and startup validation
- [todo] Modular monolith extraction without behavior changes
- [todo] PostgreSQL/Redis integration test path
- [todo] Structured logging, request IDs, and health readiness
- [todo] CI quality/security gates with verified action references
- [todo] Baseline performance measurement

## Open decisions

- Production provider and budget remain deployment decisions after measured staging results.
- Password hashing migration, PostgreSQL RLS, token versions and MFA are phase 1+ decisions.
- Retention and PDPL assumptions require legal review before go-live.
