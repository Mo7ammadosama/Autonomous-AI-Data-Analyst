-- ═══════════════════════════════════════════════════════════════
--  DataMind AI Analytics Platform — PostgreSQL Initialization
--  Runs once when the PostgreSQL container is first created
-- ═══════════════════════════════════════════════════════════════

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- fuzzy text search
CREATE EXTENSION IF NOT EXISTS "vector";    -- pgvector: semantic search

-- Grant base privileges
GRANT ALL PRIVILEGES ON DATABASE datamind TO datamind;

-- ── Application role for RLS ──────────────────────────────────
-- The FastAPI app sets: SET LOCAL app.current_user_id = '<uuid>'
-- before executing any user-scoped query. RLS policies then use
-- current_app_user_id() to filter rows at the database level.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'datamind_app') THEN
    CREATE ROLE datamind_app LOGIN PASSWORD 'datamind_app_secret';
  END IF;
END$$;

GRANT CONNECT ON DATABASE datamind TO datamind_app;
GRANT USAGE ON SCHEMA public TO datamind_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO datamind_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO datamind_app;

-- ── RLS helper: current authenticated user ────────────────────
CREATE OR REPLACE FUNCTION current_app_user_id() RETURNS TEXT AS $$
  SELECT current_setting('app.current_user_id', true);
$$ LANGUAGE SQL STABLE;

-- ── Row Level Security policies ───────────────────────────────
-- Applied in idempotent DO blocks so re-running is safe.
-- Each table gets:
--   1. An isolation policy (app role sees only its own rows)
--   2. A superuser bypass (migration/admin role sees all rows)

DO $$
DECLARE
  t RECORD;
  policy_col TEXT;
BEGIN

  -- Map table → owner column
  FOR t IN VALUES
    ('datasets',          'owner_id'),
    ('dashboards',        'user_id'),
    ('alerts',            'user_id'),
    ('chat_sessions',     'user_id'),
    ('nl2sql_queries',    'user_id'),
    ('data_connections',  'user_id'),
    ('webhooks',          'user_id'),
    ('notifications',     'user_id'),
    ('api_keys',          'user_id'),
    ('scheduled_reports', 'user_id'),
    ('insights',          'owner_id'),
    ('audit_logs',        'user_id')
  LOOP
    IF EXISTS (
      SELECT FROM pg_tables
      WHERE schemaname = 'public' AND tablename = t.column1
    ) THEN
      EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t.column1);
      EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t.column1);

      -- Drop and recreate isolation policy
      EXECUTE format(
        'DROP POLICY IF EXISTS %I ON %I',
        t.column1 || '_user_isolation', t.column1
      );
      EXECUTE format(
        'CREATE POLICY %I ON %I
           USING (%I = current_app_user_id())
           WITH CHECK (%I = current_app_user_id())',
        t.column1 || '_user_isolation', t.column1, t.column2, t.column2
      );

      -- Superuser bypass (for Alembic migrations and admin tasks)
      EXECUTE format(
        'DROP POLICY IF EXISTS %I ON %I',
        t.column1 || '_superuser_bypass', t.column1
      );
      EXECUTE format(
        'CREATE POLICY %I ON %I TO datamind USING (true) WITH CHECK (true)',
        t.column1 || '_superuser_bypass', t.column1
      );

      RAISE NOTICE 'RLS enabled on table: %', t.column1;
    END IF;
  END LOOP;

END$$;
