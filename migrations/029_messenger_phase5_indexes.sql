CREATE INDEX IF NOT EXISTS idx_chat_conversations_tenant_type_updated
  ON chat_conversations (tenant_id, conversation_type, updated_at DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_reads_tenant_user_conversation
  ON chat_reads (tenant_id, user_id, conversation_id, last_read_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_reactions_message_reaction_created
  ON chat_reactions (message_id, reaction, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_announcement_rooms_tenant_scope_active
  ON announcement_rooms (tenant_id, scope_type, is_active, created_at DESC);
