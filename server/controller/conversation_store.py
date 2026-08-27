import json
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from models.chat import AgentType, ChatMessage, ConversationSummary


class ConversationOwnershipError(Exception):
    pass


class ConversationStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @staticmethod
    def _user_conversations_key(mongo_user_id: str) -> str:
        return f"supportflow:user:{mongo_user_id}:conversations"

    @staticmethod
    def _metadata_key(conversation_id: UUID) -> str:
        return f"supportflow:conversation:{conversation_id}:meta"

    @staticmethod
    def _messages_key(conversation_id: UUID) -> str:
        return f"supportflow:conversation:{conversation_id}:messages"

    async def ensure_conversation(
        self,
        *,
        mongo_user_id: str,
        conversation_id: UUID,
        agent_type: AgentType,
        first_question: str,
    ) -> None:
        metadata_key = self._metadata_key(conversation_id)
        owner = await self.redis.hget(metadata_key, "mongo_user_id")
        if owner is not None and owner != mongo_user_id:
            raise ConversationOwnershipError(
                "The conversation does not belong to this user."
            )

        now = datetime.now(UTC)
        title = " ".join(first_question.split())[:80]
        mapping = {
            "mongo_user_id": mongo_user_id,
            "agent_type": agent_type,
            "updated_at": now.isoformat(),
        }
        if owner is None:
            mapping["title"] = title or "New conversation"
            mapping["created_at"] = now.isoformat()
        await self.redis.hset(metadata_key, mapping=mapping)
        await self.redis.zadd(
            self._user_conversations_key(mongo_user_id),
            {str(conversation_id): now.timestamp()},
        )

    async def get_agent_type(
        self,
        *,
        mongo_user_id: str,
        conversation_id: UUID,
    ) -> AgentType | None:
        metadata = await self.redis.hgetall(
            self._metadata_key(conversation_id)
        )
        if not metadata:
            return None
        if metadata.get("mongo_user_id") != mongo_user_id:
            raise ConversationOwnershipError(
                "The conversation does not belong to this user."
            )
        agent_type = metadata.get("agent_type")
        return agent_type if agent_type else None

    async def append_message(
        self,
        *,
        conversation_id: UUID,
        role: str,
        content: str,
        agent_type: AgentType | None = None,
        citations: list[str] | None = None,
    ) -> str:
        fields = {
            "role": role,
            "content": content,
            "agent_type": agent_type or "",
            "citations": json.dumps(citations or []),
            "created_at": datetime.now(UTC).isoformat(),
        }
        return await self.redis.xadd(
            self._messages_key(conversation_id),
            fields,
        )

    async def list_conversations(
        self,
        *,
        mongo_user_id: str,
        limit: int = 50,
    ) -> list[ConversationSummary]:
        entries = await self.redis.zrevrange(
            self._user_conversations_key(mongo_user_id),
            0,
            max(limit - 1, 0),
            withscores=True,
        )
        if not entries:
            return []

        pipeline = self.redis.pipeline()
        for conversation_id, _ in entries:
            pipeline.hgetall(self._metadata_key(UUID(conversation_id)))
        metadata_rows = await pipeline.execute()

        conversations: list[ConversationSummary] = []
        for (conversation_id, score), metadata in zip(
            entries,
            metadata_rows,
            strict=True,
        ):
            if not metadata:
                continue
            conversations.append(
                ConversationSummary(
                    conversation_id=UUID(conversation_id),
                    title=metadata.get("title", "New conversation"),
                    agent_type=metadata.get("agent_type", "general"),
                    updated_at=datetime.fromtimestamp(score, UTC),
                )
            )
        return conversations

    async def rename_conversation(
        self,
        *,
        mongo_user_id: str,
        conversation_id: UUID,
        title: str,
    ) -> ConversationSummary:
        metadata_key = self._metadata_key(conversation_id)
        metadata = await self.redis.hgetall(metadata_key)
        if (
            not metadata
            or metadata.get("mongo_user_id") != mongo_user_id
        ):
            raise ConversationOwnershipError(
                "Conversation was not found for this user."
            )

        now = datetime.now(UTC)
        await self.redis.hset(
            metadata_key,
            mapping={
                "title": title,
                "updated_at": now.isoformat(),
            },
        )
        await self.redis.zadd(
            self._user_conversations_key(mongo_user_id),
            {str(conversation_id): now.timestamp()},
        )
        return ConversationSummary(
            conversation_id=conversation_id,
            title=title,
            agent_type=metadata.get("agent_type", "general"),
            updated_at=now,
        )

    async def delete_conversation(
        self,
        *,
        mongo_user_id: str,
        conversation_id: UUID,
    ) -> None:
        metadata_key = self._metadata_key(conversation_id)
        metadata = await self.redis.hgetall(metadata_key)
        if (
            not metadata
            or metadata.get("mongo_user_id") != mongo_user_id
        ):
            raise ConversationOwnershipError(
                "Conversation was not found for this user."
            )

        thread_fragment = f"{mongo_user_id}:{conversation_id}"
        checkpoint_keys = [
            key
            async for key in self.redis.scan_iter(
                match=f"*{thread_fragment}*",
                count=100,
            )
        ]

        pipeline = self.redis.pipeline()
        pipeline.delete(metadata_key)
        pipeline.delete(self._messages_key(conversation_id))
        pipeline.zrem(
            self._user_conversations_key(mongo_user_id),
            str(conversation_id),
        )
        for key in checkpoint_keys:
            pipeline.delete(key)
        await pipeline.execute()

    async def get_messages(
        self,
        *,
        mongo_user_id: str,
        conversation_id: UUID,
        limit: int = 200,
    ) -> list[ChatMessage]:
        metadata = await self.redis.hgetall(
            self._metadata_key(conversation_id)
        )
        if (
            not metadata
            or metadata.get("mongo_user_id") != mongo_user_id
        ):
            raise ConversationOwnershipError(
                "Conversation was not found for this user."
            )

        entries = await self.redis.xrange(
            self._messages_key(conversation_id),
            count=limit,
        )
        messages: list[ChatMessage] = []
        for message_id, fields in entries:
            messages.append(
                ChatMessage(
                    id=message_id,
                    role=fields["role"],
                    content=fields["content"],
                    agent_type=fields.get("agent_type") or None,
                    citations=json.loads(fields.get("citations", "[]")),
                    created_at=datetime.fromisoformat(fields["created_at"]),
                )
            )
        return messages
