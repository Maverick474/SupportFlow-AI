from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


AgentType = Literal["technical", "billing", "account", "policy", "general"]
Visibility = Literal["public", "internal"]


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
    verdict: Literal["pass", "revise", "escalate", "refuse"]
    final_answer: str
    citations: list[str]
    revision_count: int


class ConversationSummary(BaseModel):
    conversation_id: UUID
    title: str
    agent_type: AgentType
    updated_at: datetime


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    agent_type: AgentType | None = None
    citations: list[str] = Field(default_factory=list)
    created_at: datetime


class KnowledgeIngestResponse(BaseModel):
    document: str
    pages: int
    chunks: int
    vector_dimensions: int
