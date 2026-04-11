-- Forward-only retirement for messenger and meetings.
-- Take a database backup/snapshot before applying this outside disposable verification.

DELETE FROM groupware_rollout_checks
WHERE module_key IN ('messenger', 'meetings');

DROP INDEX IF EXISTS idx_meeting_chat_links_room_created;
DROP INDEX IF EXISTS idx_meeting_sessions_room_state_started;
DROP INDEX IF EXISTS idx_meeting_participants_room_user;
DROP INDEX IF EXISTS idx_meeting_events_room_created;
DROP INDEX IF EXISTS idx_meeting_participants_room_joined;
DROP INDEX IF EXISTS idx_meeting_rooms_tenant_state_scheduled;

DROP INDEX IF EXISTS idx_announcement_rooms_tenant_scope_active;
DROP INDEX IF EXISTS idx_chat_reactions_message_reaction_created;
DROP INDEX IF EXISTS idx_chat_reads_tenant_user_conversation;
DROP INDEX IF EXISTS idx_chat_conversations_tenant_type_updated;
DROP INDEX IF EXISTS idx_presence_sessions_user_last_seen;
DROP INDEX IF EXISTS idx_chat_messages_conversation_created;
DROP INDEX IF EXISTS idx_chat_members_user_conversation;
DROP INDEX IF EXISTS idx_chat_conversations_tenant_created;

DROP TABLE IF EXISTS meeting_chat_links;
DROP TABLE IF EXISTS meeting_events;
DROP TABLE IF EXISTS meeting_sessions;
DROP TABLE IF EXISTS meeting_participants;
DROP TABLE IF EXISTS meeting_rooms;

DROP TABLE IF EXISTS announcement_rooms;
DROP TABLE IF EXISTS chat_polls;
DROP TABLE IF EXISTS chat_reactions;
DROP TABLE IF EXISTS chat_reads;
DROP TABLE IF EXISTS chat_attachments;
DROP TABLE IF EXISTS chat_messages;
DROP TABLE IF EXISTS chat_members;
DROP TABLE IF EXISTS chat_conversations;
DROP TABLE IF EXISTS presence_sessions;
