# Performance baseline — phase 0

This is a build and local smoke baseline, not a production capacity claim. A PostgreSQL/Redis load run and the approved 50,000-product/5,000,000-movement dataset require Docker or a staging environment and remain open.

## Evidence captured 2026-11-20

- Frontend command: `npm ci --prefix dashboard && npm run build --prefix dashboard`
- Vite build completed successfully.
- Generated assets: JavaScript `262,706` bytes and CSS `26,900` bytes before gzip. The build output reported JavaScript gzip size `80.83 kB` and CSS gzip size `6.21 kB`.
- Backend smoke suite: `pytest -q backend` completed with 4 tests passing and one migration test skipped without `TEST_DATABASE_URL` at the time of the baseline.

## Not measured yet

- p95 read/write latency at 50 concurrent users.
- PostgreSQL query plans and N+1 query count on production-shaped data.
- 100,000-product stress test and 5,000,000 movement dataset.
- LCP on emulated 4G and Lighthouse budgets.
