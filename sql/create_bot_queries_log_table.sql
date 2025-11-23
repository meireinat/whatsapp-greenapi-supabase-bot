-- Create bot_queries_log table for logging all user interactions
CREATE TABLE IF NOT EXISTS public.bot_queries_log (
    id BIGSERIAL PRIMARY KEY,
    user_phone TEXT NOT NULL,
    user_text TEXT NOT NULL,
    intent TEXT,
    parameters JSONB,
    response_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on user_phone for faster lookups
CREATE INDEX IF NOT EXISTS idx_bot_queries_log_user_phone ON public.bot_queries_log(user_phone);

-- Create index on created_at for time-based queries
CREATE INDEX IF NOT EXISTS idx_bot_queries_log_created_at ON public.bot_queries_log(created_at);

-- Create index on intent for analytics
CREATE INDEX IF NOT EXISTS idx_bot_queries_log_intent ON public.bot_queries_log(intent);

-- Enable Row Level Security (RLS)
ALTER TABLE public.bot_queries_log ENABLE ROW LEVEL SECURITY;

-- Create policy to allow service role to insert/select all rows
CREATE POLICY "Service role can manage bot_queries_log"
    ON public.bot_queries_log
    FOR ALL
    USING (auth.role() = 'service_role');

-- Grant necessary permissions
GRANT ALL ON public.bot_queries_log TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.bot_queries_log_id_seq TO service_role;

