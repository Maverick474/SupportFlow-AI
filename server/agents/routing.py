import re

from langsmith import traceable

from models.chat import AgentType


AGENT_KEYWORDS: dict[AgentType, tuple[str, ...]] = {
    "ticket": (),
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
        "policies",
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
        r"\b(?:open|create|generate|raise|submit|log|file|make) "
        r"(?:me )?(?:a )?(?:(?:support|technical|billing|account|policy) )?"
        r"(?:ticket|case)\b",
        r"\b(?:need|want|request|would like) (?:a )?"
        r"(?:(?:support|technical|billing|account|policy) )?"
        r"(?:ticket|case)\b",
        r"\b(?:need|want|request|would like) (?:a )?"
        r"(?:human agent|human support|representative)\b",
        r"\b(?:please )?escalate (?:this|it|my request|my issue|the issue)\b",
        r"\b(?:speak|talk|connect) (?:me )?(?:to|with) (?:a )?"
        r"(?:human|representative|agent)\b",
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


_ACTIVE_INCIDENT_SUBJECT = re.compile(
    r"\b(?:i|i'm|i am|i've|i have|me|my|mine|we|we're|we are|"
    r"we've|we have|us|our|ours)\b"
)
_ACCOUNT_ACCESS_BLOCKED = re.compile(
    r"\b(?:can(?:not|'t)|could(?: not|n't)|unable to)\s+"
    r"(?:(?:access|open)\s+(?:my|our|the)\s+account|"
    r"(?:log|sign)[\s-]?in(?:to\s+(?:my|our|the)\s+account)?)\b|"
    r"\blocked out of (?:my|our|the) account\b|"
    r"\blost access to (?:my|our|the) account\b"
)
_REPEATED_UNRESOLVED_FAILURE = re.compile(
    r"\b(?:"
    r"(?:multiple|several|repeated|many)\s+(?:failed\s+)?"
    r"(?:attempts?|tries)|"
    r"(?:tried|attempted)(?:\s+\w+){0,8}\s+"
    r"(?:twice|three times|multiple times|several times|repeatedly)|"
    r"(?:tried|attempted)(?:\s+\w+){0,8}\s+(?:but|and)\s+"
    r"(?:it\s+)?(?:still\s+)?(?:fails?|failing|does(?:n't| not)\s+work|"
    r"is(?:n't| not)\s+working)|"
    r"(?:after|despite)\s+(?:multiple|several|repeated|many)\s+"
    r"(?:attempts?|tries)|"
    r"(?:it\s+)?still\s+(?:fails?|failing|does(?:n't| not)\s+work|"
    r"is(?:n't| not)\s+working)|"
    r"keeps?\s+(?:failing|crashing)"
    r")\b"
)
_LIVE_SUPPORT_ACTION = re.compile(
    r"\b(?:(?:can|could|would|will) you|please)\s+"
    r"(?:refund|cancel|unlock|restore|change|update|delete|remove|"
    r"disable|enable|resend|reset)\b"
)


def is_explicit_ticket_request(question: str) -> bool:
    """Return whether the user explicitly requested a ticket or a human."""
    normalized = " ".join(question.casefold().split())
    return any(
        re.search(pattern, normalized)
        for pattern in AGENT_PATTERNS["ticket"]
    ) or any(
        re.search(rf"\b{re.escape(keyword)}\b", normalized)
        for keyword in AGENT_KEYWORDS["ticket"]
    )


def is_ticket_worthy_incident(
    question: str,
    agent_type: AgentType,
) -> bool:
    """Identify a blocked account or repeated unresolved customer incident."""
    if agent_type not in {"technical", "billing", "account"}:
        return False
    normalized = " ".join(question.casefold().split())
    if not _ACTIVE_INCIDENT_SUBJECT.search(normalized):
        return False
    return bool(
        _ACCOUNT_ACCESS_BLOCKED.search(normalized)
        or _REPEATED_UNRESOLVED_FAILURE.search(normalized)
    )


def requires_live_support_action(question: str) -> bool:
    """Identify a request for an action the chat agent cannot perform."""
    normalized = " ".join(question.casefold().split())
    return bool(_LIVE_SUPPORT_ACTION.search(normalized))


def should_create_ticket(
    question: str,
    *,
    agent_type: AgentType,
) -> bool:
    """Gate tickets to explicit, blocked, repeated, or privileged requests."""
    return (
        is_explicit_ticket_request(question)
        or is_ticket_worthy_incident(question, agent_type)
        or requires_live_support_action(question)
    )


@traceable(
    name="supportflow.agent-router",
    run_type="chain",
    tags=["supportflow", "agent:router"],
)
def route_agent_type(
    question: str,
    requested_agent: AgentType | None = None,
) -> AgentType:
    # A restored Ticket conversation must not turn an informational follow-up
    # into a new ticket. Ticket intent is determined from the message below;
    # explicit knowledge-agent selections still override automatic routing.
    if requested_agent is not None and requested_agent != "ticket":
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
