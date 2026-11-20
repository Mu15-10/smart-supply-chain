# Architecture

The target is a modular monolith for a multi-tenant supply-chain SaaS. The API owns authentication, catalog, inventory, purchasing, audit, integrations, imports and reporting boundaries. PostgreSQL is the system of record; Redis provides ephemeral security and cache state. A separate worker will process durable background work after the foundation gate.

The current implementation is still a single FastAPI module and retains the existing service routing for compatibility during phase 0. Extraction must preserve public routes and response shapes.

## Phase 0 compatibility

The public API remains unversioned during the foundation gate. No endpoint response shape is intentionally changed by the foundation work.
