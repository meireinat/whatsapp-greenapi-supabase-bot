-- Create a policy to allow anon key to read from containers table
-- This allows the anon key to work with RLS enabled

-- First, enable RLS if not already enabled
ALTER TABLE containers ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows anon role to SELECT from containers
CREATE POLICY "Allow anon read containers" 
ON containers 
FOR SELECT 
TO anon 
USING (true);

-- Verify the policy was created
SELECT 
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd
FROM pg_policies
WHERE tablename = 'containers';

