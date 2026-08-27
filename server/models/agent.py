import operator
from typing import Annotated, Literal, TypedDict
from uuid import UUID

from pydantic import BaseModel, Field

from models.chat import AgentType, Visibility


class DraftAnswer(BaseModel):
    answer: str = Field(
        description="Concise customer-facing answer with inline handbook citations."
    )
    citations: list[str] = Field(
        description="Exact source labels used in the answer."
    )
    requires_human_review: bool
    uncertainty: str = Field(
        description="Unknown information, or an empty string."
    )


class ClaimAudit(BaseModel):
    claim: str = Field(
        description="One atomic factual claim from the candidate answer."
    )
    supported: bool
    source_label: str = Field(
        description="Exact supporting source label, or an empty string."
    )
    evidence_quote: str = Field(
        description=(
            "Shortest exact evidence quote supporting the full claim, "
            "or an empty string."
        )
    )
    reason: str = Field(
        description="Why the evidence does or does not support the full claim."
    )


class ValidationResult(BaseModel):
    verdict: Literal["pass", "revise", "escalate", "refuse"]
    grounded: bool
    citations_valid: bool
    claim_audits: list[ClaimAudit]
    unsupported_claims: list[str]
    feedback: str


class AgentConfig(BaseModel):
    id: UUID | None = None
    workspace_id: UUID
    name: str
    agent_type: AgentType
    description: str = ""
    system_prompt: str = ""
    generator_model: str = "openai/gpt-4o-mini"
    validator_model: str = "openai/gpt-4.1-mini"


class AgentState(TypedDict, total=False):
    question: str
    workspace_id: str
    agent_type: AgentType
    agent_name: str
    agent_system_prompt: str
    generator_model: str
    validator_model: str
    user_visibility: Visibility
    conversation_history: Annotated[list[dict[str, str]], operator.add]
    retrieval_query: str
    retrieved_passages: list[str]
    retrieved_chunk_ids: list[str]
    draft: DraftAnswer
    validation: ValidationResult
    revision_count: int
    final_answer: str
