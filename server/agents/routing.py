import re

from langsmith import traceable

from models.chat import AgentType


AGENT_KEYWORDS: dict[AgentType, tuple[str, ...]] = {
    "ticket": (
        "human agent",
        "human support",
        "representative",
        "escalate",
        "escalation",
    ),
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


AGENT_PATTERNS: dict[AgentType, tuple[str, ...]] = {
    "ticket": (
        r"\b(?:open|create|raise|submit|need) (?:a )?(?:support )?(?:ticket|case)\b",
        r"\b(?:speak|talk) (?:to|with) (?:a )?(?:human|representative|agent)\b",
    ),
    "billing": (),
    "account": (),
    "policy": (),
    "technical": (
        r"\bweb[\s-]?hooks?\b",
        r"\btrouble[\s-]?shoot(?:ing|s|ed)?\b",
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
    for agent_type in ("ticket", "billing", "account", "policy", "technical"):
        if any(
            re.search(pattern, normalized)
            for pattern in AGENT_PATTERNS[agent_type]
        ):
            return agent_type
        if any(
            re.search(rf"\b{re.escape(keyword)}\b", normalized)
            for keyword in AGENT_KEYWORDS[agent_type]
        ):
            return agent_type
    return "general"
