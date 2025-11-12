-- Disable RLS on containers table (for testing only)
-- WARNING: This is not recommended for production!
-- Use service_role key or create proper RLS policies instead.

ALTER TABLE containers DISABLE ROW LEVEL SECURITY;

-- Verify RLS is disabled
SELECT 
    tablename, 
    rowsecurity as "RLS Enabled"
FROM pg_tables 
WHERE schemaname = 'public' 
  AND tablename = 'containers';

