import logging
import re
from functools import lru_cache
from typing import Literal
from uuid import UUID

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langsmith import traceable
from pydantic import BaseModel, Field

from controller.config import Settings
from models.chat import AgentType


logger = logging.getLogger(__name__)

MAX_COMPLETION_TOKENS = 1_000


class TicketDraft(BaseModel):
    title: str = Field(description="Short, specific support-ticket title.")
    summary: str = Field(
        description=(
            "Concise description of the customer's issue and relevant context."
        )
    )
    category: Literal[
        "technical",
        "billing",
        "account",
        "policy",
        "security",
        "general",
    ]
    priority: Literal["low", "medium", "high", "urgent"]
    customer_impact: str = Field(
        description="How the reported issue affects the customer."
    )
    requested_action: str = Field(
        description="The next action requested from an authorized human."
    )


TICKET_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are the SupportFlow Ticket and Escalation Agent.

Convert an already-escalated SupportFlow request into a concise ticket for an authorized human support team. Do not answer the customer's issue and do not claim that you performed any account action.

RULES
1. Use only the supplied request, validated response, and validator feedback.
2. Never include passwords, API keys, tokens, payment details, or other secrets.
3. Do not invent account identifiers, outage facts, completed actions, or customer impact.
4. Select the closest category. Use security only for a legitimate security or privacy incident.
5. Use urgent only for an active security incident, material data-loss risk, or critical outage. Use high for a blocked customer or repeated failure requiring prompt human action. Otherwise use medium or low.
6. The requested action must describe what an authorized human should review or perform.
7. Return only the fields required by the TicketDraft schema.""",
        ),
        (
            "human",
            """<source_agent>{source_agent}</source_agent>

<customer_request>
{question}
</customer_request>

<validated_response>
{final_answer}
</validated_response>

<validator_feedback>
{validator_feedback}
</validator_feedback>""",
        ),
    ]
)


def ticket_reference(ticket_id: UUID) -> str:
    return f"SFA-{ticket_id.hex[:8].upper()}"


class TicketAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @lru_cache(maxsize=8)
    def _chain(self, model_name: str):
        llm = ChatOpenAI(
            base_url=self.settings.openrouter_base_url,
            api_key=self.settings.openrouter_key,
            model=model_name,
            temperature=0.0,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        )
        structured_llm = llm.with_structured_output(
            TicketDraft,
            method="json_schema",
            strict=True,
        )
        return (TICKET_PROMPT | structured_llm).with_config(
            {
                "run_name": "supportflow.ticket-agent",
                "tags": ["supportflow", "agent:ticket", "workflow:escalation"],
            }
        )

    @traceable(
        name="supportflow.ticket-draft",
        run_type="chain",
        tags=["supportflow", "agent:ticket"],
    )
    def create_draft(
        self,
        *,
        model_name: str,
        source_agent: AgentType,
        question: str,
        final_answer: str,
        validator_feedback: str,
    ) -> TicketDraft:
        try:
            return self._chain(model_name).invoke(
                {
                    "source_agent": source_agent,
                    "question": question,
                    "final_answer": final_answer,
                    "validator_feedback": validator_feedback,
                }
            )
        except Exception:
            logger.exception(
                "Ticket model failed; using a deterministic ticket draft."
            )
            return self._fallback_draft(
                source_agent=source_agent,
                question=question,
            )

    @staticmethod
    def _fallback_draft(
        *,
        source_agent: AgentType,
        question: str,
    ) -> TicketDraft:
        clean_question = re.sub(r"\s+", " ", question).strip()
        title = clean_question[:117]
        if len(clean_question) > 117:
            title = f"{title.rstrip()}..."
        if not title:
            title = "Support request requiring human review"

        category = source_agent if source_agent != "ticket" else "general"
        priority = "medium"
        normalized = clean_question.casefold()
        if any(
            phrase in normalized
            for phrase in (
                "account compromised",
                "data loss",
                "security breach",
                "service down",
                "complete outage",
            )
        ):
            priority = "urgent"
        elif any(
            phrase in normalized
            for phrase in ("blocked", "cannot access", "repeatedly fails")
        ):
            priority = "high"

        return TicketDraft(
            title=title,
            summary=clean_question,
            category=category,
            priority=priority,
            customer_impact="The exact customer impact requires human confirmation.",
            requested_action=(
                "Review the request, verify the customer and relevant live data, "
                "then take the authorized next action."
            ),
        )
