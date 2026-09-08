BEGIN;

SET LOCAL lock_timeout = '5s';

-- History is accessed only through the FastAPI server's database connection.
ALTER TABLE public.daily_assignments ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.daily_assignments FROM PUBLIC, anon, authenticated;

COMMIT;
