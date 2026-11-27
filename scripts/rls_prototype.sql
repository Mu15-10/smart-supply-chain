\set ON_ERROR_STOP on
\timing on

-- Run as a PostgreSQL superuser on the disposable supply_ci database.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supply_rls_owner') THEN
    CREATE ROLE supply_rls_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supply_rls_app') THEN
    CREATE ROLE supply_rls_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
  END IF;
END
$$;

DROP SCHEMA IF EXISTS rls_probe CASCADE;
CREATE SCHEMA rls_probe AUTHORIZATION supply_rls_owner;
SET ROLE supply_rls_owner;
CREATE TABLE rls_probe.suppliers_probe (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id text NOT NULL,
  name text NOT NULL
);
CREATE TABLE rls_probe.inventory_probe (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id text NOT NULL,
  quantity integer NOT NULL
);
INSERT INTO rls_probe.suppliers_probe (tenant_id, name)
SELECT CASE WHEN n % 2 = 0 THEN 'tenant-a' ELSE 'tenant-b' END, 'supplier-' || n
FROM generate_series(1, 10000) AS series(n);
INSERT INTO rls_probe.inventory_probe (tenant_id, quantity)
SELECT CASE WHEN n % 2 = 0 THEN 'tenant-a' ELSE 'tenant-b' END, n
FROM generate_series(1, 10000) AS series(n);
CREATE INDEX suppliers_probe_tenant_idx ON rls_probe.suppliers_probe (tenant_id);
CREATE INDEX inventory_probe_tenant_idx ON rls_probe.inventory_probe (tenant_id);
GRANT USAGE ON SCHEMA rls_probe TO supply_rls_app;
GRANT SELECT ON rls_probe.suppliers_probe, rls_probe.inventory_probe TO supply_rls_app;
RESET ROLE;

-- Baseline: application role can query both rows for a tenant predicate.
SET ROLE supply_rls_app;
BEGIN;
SET LOCAL app.tenant_id = 'tenant-a';
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT count(*) FROM rls_probe.suppliers_probe WHERE tenant_id = current_setting('app.tenant_id');
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT count(*) FROM rls_probe.inventory_probe WHERE tenant_id = current_setting('app.tenant_id');
COMMIT;
RESET ROLE;

-- Prototype: owner enables FORCE RLS and policies use the transaction/session setting.
SET ROLE supply_rls_owner;
ALTER TABLE rls_probe.suppliers_probe ENABLE ROW LEVEL SECURITY;
ALTER TABLE rls_probe.suppliers_probe FORCE ROW LEVEL SECURITY;
CREATE POLICY suppliers_tenant_policy
  ON rls_probe.suppliers_probe USING (tenant_id = current_setting('app.tenant_id', true));
ALTER TABLE rls_probe.inventory_probe ENABLE ROW LEVEL SECURITY;
ALTER TABLE rls_probe.inventory_probe FORCE ROW LEVEL SECURITY;
CREATE POLICY inventory_tenant_policy
  ON rls_probe.inventory_probe USING (tenant_id = current_setting('app.tenant_id', true));
RESET ROLE;

SET ROLE supply_rls_app;
BEGIN;
SET LOCAL app.tenant_id = 'tenant-a';
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT count(*) FROM rls_probe.suppliers_probe;
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT count(*) FROM rls_probe.inventory_probe;
SELECT (SELECT count(*) FROM rls_probe.suppliers_probe) AS suppliers_visible,
       (SELECT count(*) FROM rls_probe.inventory_probe) AS inventory_visible;
COMMIT;
RESET ROLE;

-- Verify the application role cannot bypass RLS and cannot read the other tenant.
SET ROLE supply_rls_app;
BEGIN;
SET LOCAL app.tenant_id = 'tenant-b';
SELECT (SELECT count(*) FROM rls_probe.suppliers_probe) AS suppliers_visible,
       (SELECT count(*) FROM rls_probe.inventory_probe) AS inventory_visible;
COMMIT;
RESET ROLE;

DROP SCHEMA rls_probe CASCADE;
DROP ROLE supply_rls_app;
DROP ROLE supply_rls_owner;
