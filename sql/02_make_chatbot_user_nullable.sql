-- Migration: Make chatbot_sessions.user_id nullable
-- Run this on production DB if currently user_id is NOT NULL and you want to allow anonymous sessions.

ALTER TABLE chatbot_sessions
    ALTER COLUMN user_id DROP NOT NULL;

-- Optional: ensure FK behaviour is SET NULL on delete (if not already):
-- ALTER TABLE chatbot_sessions
--     DROP CONSTRAINT IF EXISTS chatbot_sessions_user_id_fkey;
-- ALTER TABLE chatbot_sessions
--     ADD CONSTRAINT chatbot_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
