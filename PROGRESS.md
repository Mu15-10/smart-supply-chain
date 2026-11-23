# Project progress

## Current gate

- Phase: `1-b-fix` — trusted proxy and refresh-family security remediation
- Branch: `hardening/phase-0`
- Status: `done; awaiting written approval for 1-c`
- Last verified commit: `f6ab425`

## Decisions

- Multi-tenant SaaS for distribution and trading companies in Saudi Arabia first.
- Arabic/RTL first; country packs will make currency, tax, locale and timezone configurable.
- Production public registration is disabled; development may enable it.
- MongoDB is planned for removal after the foundation gate; no removal is performed in 1-b-fix.
- Modular monolith with one API and a separate worker is the target architecture.
- MIT license is used as the default for this public repository.

## Phase 0 and 1-b tasks

- [done] Documentation and repository hygiene
- [done] Explicit Alembic DDL and round-trip migration test on PostgreSQL
- [done] Central settings and startup validation (initial foundation)
- [blocked] Modular monolith extraction requires a larger behavior-preserving refactor and remains open in phase 0
- [done] PostgreSQL/Redis integration test path with real local services and CI services
- [doing] Request IDs and health readiness; structured JSON logging remains open
- [done] Foundation CI published and green on `f6ab425`
- [done] Local build baseline; load baseline remains open
- [done] 1-b trusted proxy CIDR/XFF remediation, refresh-family logout/reuse hardening, and staging acceptance criteria
- [blocked] 1-c tenant isolation and authorization requires written manager approval

## Open decisions

- Production provider and budget remain deployment decisions after measured staging results.
- Password hashing migration, PostgreSQL RLS, token versions and MFA remain future units.
- Retention and PDPL assumptions require legal review before go-live.
