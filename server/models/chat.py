from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


AgentType = Literal[
    "technical",
    "billing",
    "account",
    "policy",
    "general",
    "ticket",
]
Visibility = Literal["public", "internal"]
Verdict = Literal["pass", "revise", "escalate", "refuse"]


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=8_000)
    conversation_id: UUID | None = None
    ticket_id: UUID | None = None
    agent_type: AgentType | None = None
    user_visibility: Visibility = "public"


class ChatResponse(BaseModel):
    conversation_id: UUID
    run_id: UUID | None = None
    agent_type: AgentType
    verdict: Verdict
    final_answer: str
    citations: list[str]
    revision_count: int
    ticket_id: UUID | None = None
    ticket_reference: str | None = None
    ticket_status: Literal["open"] | None = None
    ticket_priority: Literal["low", "medium", "high", "urgent"] | None = None


class ConversationSummary(BaseModel):
    conversation_id: UUID
    title: str
    agent_type: AgentType
    updated_at: datetime


class ConversationRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Conversation title cannot be empty.")
        return normalized


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    agent_type: AgentType | None = None
    verdict: Verdict | None = None
    citations: list[str] = Field(default_factory=list)
    created_at: datetime


class KnowledgeIngestResponse(BaseModel):
    document: str
    pages: int
    chunks: int
    vector_dimensions: int
