import re

from langsmith import traceable

from models.chat import AgentType


AGENT_KEYWORDS: dict[AgentType, tuple[str, ...]] = {
    "billing": (
        "bill",
        "billing",
        "charge",
        "charged",
        "invoice",
        "payment",
        "refund",
        "subscription",
        "plan",
    ),
    "account": (
        "account",
        "email",
        "login",
        "log in",
        "sign-in",
        "password",
        "mfa",
        "verification",
    ),
    "policy": (
        "policy",
        "privacy",
        "retention",
        "security",
        "permission",
        "role",
        "export",
        "legal",
    ),
    "technical": (
        "api",
        "error",
        "webhook",
        "integration",
        "outage",
        "slack",
        "browser",
        "pdf",
        "preview",
    ),
    "general": (),
}


@traceable(
    name="supportflow.agent-router",
    run_type="chain",
    tags=["supportflow", "agent:router"],
)
def route_agent_type(
    question: str,
    requested_agent: AgentType | None = None,
) -> AgentType:
    if requested_agent is not None:
        return requested_agent

    normalized = question.casefold()
    for agent_type in ("billing", "account", "policy", "technical"):
        if any(
            re.search(rf"\b{re.escape(keyword)}\b", normalized)
            for keyword in AGENT_KEYWORDS[agent_type]
        ):
            return agent_type
    return "general"
