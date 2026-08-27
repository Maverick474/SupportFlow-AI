import re
from functools import lru_cache
from typing import Literal
from uuid import UUID

from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.redis import RedisSaver
from langgraph.graph import END, START, StateGraph
from redis import Redis

from agents.prompts import GENERATOR_PROMPT, REFINER_PROMPT, VALIDATOR_PROMPT
from controller.config import Settings
from models.agent import AgentState, ClaimAudit, DraftAnswer, ValidationResult
from service.knowledge import (
    AgentRecordRepository,
    create_embedding_model,
    extract_section_title,
)


MAX_COMPLETION_TOKENS = 1_000
MAX_REVISIONS = 2


def format_conversation_history(state: AgentState, limit: int = 3) -> str:
    turns = state.get("conversation_history", [])[-limit:]
    if not turns:
        return "(no earlier turns)"

    formatted_turns: list[str] = []
    for turn in turns:
        formatted_turns.append(f"User: {turn['question']}")
        if turn.get("verdict") == "pass":
            formatted_turns.append(f"Assistant: {turn['answer']}")
    return "\n".join(formatted_turns)


def is_contextual_follow_up(question: str) -> bool:
    normalized = normalize_evidence_text(question).casefold()
    if normalized.startswith(
        (
            "and ",
            "also ",
            "then ",
            "what if ",
            "how about ",
            "what about ",
            "why is that",
            "why does that",
        )
    ):
        return True
    return bool(
        re.search(
            r"\b(it|its|that|this|they|them|their|those|these|"
            r"former|latter|same|previous|above)\b",
            normalized,
        )
    )


def build_retrieval_query(state: AgentState) -> str:
    question = state["question"]
    turns = state.get("conversation_history", [])
    if not turns or not is_contextual_follow_up(question):
        return question

    prior_questions = [
        normalize_evidence_text(turn["question"])
        for turn in turns[-2:]
        if turn.get("question")
    ]
    if not prior_questions:
        return question
    context = "\n".join(f"- {item}" for item in prior_questions)
    return (
        f"Previous questions that establish the follow-up topic:\n{context}\n"
        f"Current follow-up question: {question}"
    )


def normalize_evidence_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def passages_by_source(evidence: str) -> dict[str, list[str]]:
    passages: dict[str, list[str]] = {}
    pattern = (
        r"\[Retrieved source label: ([^\]]+)\]\n"
        r"(.*?)(?=\n\n\[Retrieved source label: |\Z)"
    )
    for match in re.finditer(pattern, evidence, flags=re.DOTALL):
        label, passage = match.groups()
        passages.setdefault(label, []).append(normalize_evidence_text(passage))
    return passages


def evidence_source_labels(evidence: str) -> list[str]:
    return list(
        dict.fromkeys(
            re.findall(
                r"\[Retrieved source label: ([^\]]+)\]",
                evidence,
            )
        )
    )


def inline_source_labels(answer: str, valid_labels: list[str]) -> list[str]:
    positioned = [
        (answer.find(f"[{label}]"), label)
        for label in valid_labels
        if f"[{label}]" in answer
    ]
    return [label for _, label in sorted(positioned)]


def uncited_list_items(
    answer: str,
    valid_labels: list[str],
) -> list[str]:
    citation_tokens = [f"[{label}]" for label in valid_labels]
    return [
        line.strip()
        for line in answer.splitlines()
        if re.match(r"^\s*(?:\d+[.)]|[-*])\s+\S", line)
        and not any(token in line for token in citation_tokens)
    ]


def canonicalize_draft_citations(
    draft: DraftAnswer,
    evidence: str,
) -> DraftAnswer:
    valid_labels = evidence_source_labels(evidence)
    valid_set = set(valid_labels)
    source_passages = passages_by_source(evidence)
    aliases: dict[str, str] = {}
    for source_label, passages in source_passages.items():
        for passage in passages:
            for alias in re.findall(r"\[Source: ([^\]]+)\]", passage):
                aliases.setdefault(alias.strip(), source_label)

    answer = draft.answer
    for label in sorted(valid_labels, key=len, reverse=True):
        answer = answer.replace(f"[Source: {label}]", f"[{label}]")
    for alias, label in aliases.items():
        answer = answer.replace(f"[Source: {alias}]", f"[{label}]")

    inline_labels = inline_source_labels(answer, valid_labels)

    declared_labels: list[str] = []
    for raw_citation in draft.citations:
        citation = raw_citation.strip()
        if citation.startswith("[") and citation.endswith("]"):
            citation = citation[1:-1].strip()
        if citation.startswith("Source:"):
            citation = citation.removeprefix("Source:").strip()
        citation = aliases.get(citation, citation)
        if citation in valid_set:
            declared_labels.append(citation)

    canonical = inline_labels or list(dict.fromkeys(declared_labels))
    return draft.model_copy(
        update={
            "answer": answer,
            "citations": canonical,
        }
    )


def safe_source_part(value: object, fallback: str) -> str:
    cleaned = normalize_evidence_text(str(value or fallback))
    return cleaned.replace("[", "(").replace("]", ")")[:160]


def audit_quote_matches_source(
    audit: ClaimAudit,
    source_passages: dict[str, list[str]],
) -> bool:
    quote = normalize_evidence_text(audit.evidence_quote)
    if not quote:
        return False
    passages = source_passages.get(audit.source_label, [])
    if any(quote in passage for passage in passages):
        return True

    quote_fragments = [
        normalize_evidence_text(fragment)
        for fragment in re.split(r"(?:\.{3}|…)", quote)
        if normalize_evidence_text(fragment)
    ]
    if len(quote_fragments) < 2:
        return False
    for passage in passages:
        cursor = 0
        for fragment in quote_fragments:
            position = passage.find(fragment, cursor)
            if position < 0:
                break
            cursor = position + len(fragment)
        else:
            return True
    return False


class SupportFlowWorkflow:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: AgentRecordRepository,
        redis_client: Redis,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.embedding_model = create_embedding_model(settings)
        self.checkpointer = RedisSaver(
            redis_client=redis_client,
            ttl={"default_ttl": 1_440, "refresh_on_read": True},
        )
        self.checkpointer.setup()
        self.graph = self._build_graph()

    @lru_cache(maxsize=16)
    def _chains(self, generator_model: str, validator_model: str):
        generator_llm = ChatOpenAI(
            base_url=self.settings.openrouter_base_url,
            api_key=self.settings.openrouter_key,
            model=generator_model,
            temperature=0.2,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        )
        validator_llm = ChatOpenAI(
            base_url=self.settings.openrouter_base_url,
            api_key=self.settings.openrouter_key,
            model=validator_model,
            temperature=0.0,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        )

        generator_agent = generator_llm.with_structured_output(
            DraftAnswer,
            method="json_schema",
            strict=True,
        )
        validator_agent = validator_llm.with_structured_output(
            ValidationResult,
            method="json_schema",
            strict=True,
        )
        generator_chain = (GENERATOR_PROMPT | generator_agent).with_config(
            {
                "run_name": "supportflow.generator-agent",
                "tags": ["supportflow", "agent:generator"],
            }
        )
        validator_chain = (VALIDATOR_PROMPT | validator_agent).with_config(
            {
                "run_name": "supportflow.validator-agent",
                "tags": ["supportflow", "agent:validator"],
            }
        )
        refiner_chain = (REFINER_PROMPT | generator_agent).with_config(
            {
                "run_name": "supportflow.refiner-agent",
                "tags": ["supportflow", "agent:refiner"],
            }
        )
        return generator_chain, validator_chain, refiner_chain

    def retrieve_node(self, state: AgentState) -> dict:
        visibility = state.get("user_visibility", "public")
        retrieval_query = build_retrieval_query(state)

        query_embedding = self.embedding_model.embed_query(retrieval_query)
        selected = self.repository.similarity_search(
            workspace_id=UUID(state["workspace_id"]),
            query_embedding=query_embedding,
            visibility=visibility,
            limit=6,
        )

        passages: list[str] = []
        chunk_ids: list[str] = []
        seen_chunks: set[str] = set()
        for chunk in selected:
            metadata = chunk.get("metadata") or {}
            content = str(chunk.get("content") or "").strip()
            if not content:
                continue
            fingerprint = normalize_evidence_text(content)
            if fingerprint in seen_chunks:
                continue
            seen_chunks.add(fingerprint)

            document = safe_source_part(
                metadata.get("document"),
                "Uploaded support document",
            )
            page_number = safe_source_part(
                metadata.get("page_number"),
                "?",
            )
            section_title = safe_source_part(
                extract_section_title(
                    content,
                    str(metadata.get("section_title") or "Unknown section"),
                ),
                "Unknown section",
            )
            label = (
                f"{document}, p. {page_number}, {section_title}"
            )
            passages.append(
                f"[Retrieved source label: {label}]\n{content}"
            )
            chunk_ids.append(str(chunk["id"]))

        return {
            "retrieval_query": retrieval_query,
            "retrieved_passages": passages,
            "retrieved_chunk_ids": chunk_ids,
            "revision_count": 0,
        }

    def generate_node(self, state: AgentState) -> dict:
        generator_chain, _, _ = self._chains(
            state["generator_model"],
            state["validator_model"],
        )
        evidence = "\n\n".join(state["retrieved_passages"])
        draft = generator_chain.invoke(
            {
                "question": state["question"],
                "history": format_conversation_history(state),
                "evidence": evidence or "(no relevant evidence was retrieved)",
                "agent_name": state["agent_name"],
                "agent_type": state["agent_type"],
                "agent_system_prompt": state.get("agent_system_prompt", ""),
            }
        )
        return {"draft": canonicalize_draft_citations(draft, evidence)}

    def validate_node(self, state: AgentState) -> dict:
        _, validator_chain, _ = self._chains(
            state["generator_model"],
            state["validator_model"],
        )
        evidence = "\n\n".join(state["retrieved_passages"])
        result = validator_chain.invoke(
            {
                "question": state["question"],
                "history": format_conversation_history(state),
                "evidence": evidence or "(no relevant evidence was retrieved)",
                "answer": state["draft"].answer,
                "citations": (
                    "\n".join(state["draft"].citations) or "(none)"
                ),
            }
        )

        ordered_evidence_labels = evidence_source_labels(evidence)
        evidence_labels = set(ordered_evidence_labels)
        declared_citations = state["draft"].citations
        inline_citations = inline_source_labels(
            state["draft"].answer,
            ordered_evidence_labels,
        )
        invalid_citations = [
            citation
            for citation in declared_citations
            if citation not in evidence_labels
        ]
        missing_inline = [
            citation
            for citation in declared_citations
            if citation not in inline_citations
        ]
        undeclared_inline = [
            citation
            for citation in inline_citations
            if citation not in declared_citations
        ]
        uncited_items = uncited_list_items(
            state["draft"].answer,
            ordered_evidence_labels,
        )
        failed_audits = [
            audit.claim for audit in result.claim_audits if not audit.supported
        ]
        invalid_audit_sources = [
            audit.claim
            for audit in result.claim_audits
            if audit.supported and audit.source_label not in evidence_labels
        ]
        source_passages = passages_by_source(evidence)
        invalid_audit_quotes = [
            audit.claim
            for audit in result.claim_audits
            if audit.supported
            and not audit_quote_matches_source(audit, source_passages)
        ]

        citation_problems = bool(
            not declared_citations
            or invalid_citations
            or missing_inline
            or undeclared_inline
            or uncited_items
        )
        audit_problems = bool(
            not result.claim_audits
            or failed_audits
            or invalid_audit_sources
            or invalid_audit_quotes
        )

        if result.verdict == "pass" and (citation_problems or audit_problems):
            problems: list[str] = []
            if not declared_citations:
                problems.append("declare at least one supporting citation")
            if invalid_citations:
                problems.append("use only exact retrieved source labels")
            if missing_inline:
                problems.append("place every declared citation inline")
            if undeclared_inline:
                problems.append("declare every inline source label")
            if uncited_items:
                problems.append(
                    "add an exact inline source label to every factual list item"
                )
            if not result.claim_audits:
                problems.append("audit every atomic factual claim")
            if failed_audits:
                problems.append(
                    "remove or correct unsupported claims: "
                    + "; ".join(failed_audits[:4])
                )
            if invalid_audit_sources:
                problems.append("use exact source labels in claim audits")
            if invalid_audit_quotes:
                problems.append("use exact contiguous evidence quotes")
            result = result.model_copy(
                update={
                    "verdict": "revise",
                    "grounded": False,
                    "citations_valid": (
                        False if citation_problems else result.citations_valid
                    ),
                    "unsupported_claims": list(
                        dict.fromkeys(
                            result.unsupported_claims + failed_audits
                        )
                    ),
                    "feedback": "; ".join(problems),
                }
            )

        if (
            result.verdict == "revise"
            and state.get("revision_count", 0) >= MAX_REVISIONS
        ):
            result = result.model_copy(
                update={
                    "verdict": "escalate",
                    "feedback": "The answer remained unverified after revision.",
                }
            )
        return {"validation": result}

    def refine_node(self, state: AgentState) -> dict:
        _, _, refiner_chain = self._chains(
            state["generator_model"],
            state["validator_model"],
        )
        evidence = "\n\n".join(state["retrieved_passages"])
        revised = refiner_chain.invoke(
            {
                "question": state["question"],
                "history": format_conversation_history(state),
                "evidence": evidence or "(no relevant evidence was retrieved)",
                "answer": state["draft"].answer,
                "citations": (
                    "\n".join(state["draft"].citations) or "(none)"
                ),
                "feedback": state["validation"].feedback[:1_500],
            }
        )
        return {
            "draft": canonicalize_draft_citations(revised, evidence),
            "revision_count": state.get("revision_count", 0) + 1,
        }

    @staticmethod
    def finalize_node(state: AgentState) -> dict:
        verdict = state["validation"].verdict
        if verdict == "pass":
            final = state["draft"].answer
        elif verdict == "refuse":
            final = (
                "I can’t help with that request because it would conflict "
                "with security or privacy requirements."
            )
        else:
            final = (
                "I couldn’t verify a complete answer from the available "
                "support document. Please ask an authorized support team "
                "member to review this request."
            )
        completed_turn = {
            "question": state["question"],
            "answer": final,
            "verdict": verdict,
        }
        return {
            "final_answer": final,
            "conversation_history": (
                state.get("conversation_history", [])[-2:]
                + [completed_turn]
            ),
        }

    @staticmethod
    def route_after_validation(
        state: AgentState,
    ) -> Literal["refine", "finalize"]:
        return (
            "refine"
            if state["validation"].verdict == "revise"
            else "finalize"
        )

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node(
            "retrieve",
            RunnableLambda(self.retrieve_node).with_config(
                {
                    "run_name": "supportflow.retrieval-agent",
                    "tags": ["supportflow", "agent:retriever"],
                }
            ),
        )
        builder.add_node(
            "generate",
            RunnableLambda(self.generate_node).with_config(
                {
                    "run_name": "supportflow.generator-node",
                    "tags": ["supportflow", "agent:generator"],
                }
            ),
        )
        builder.add_node(
            "validate",
            RunnableLambda(self.validate_node).with_config(
                {
                    "run_name": "supportflow.validator-node",
                    "tags": ["supportflow", "agent:validator"],
                }
            ),
        )
        builder.add_node(
            "refine",
            RunnableLambda(self.refine_node).with_config(
                {
                    "run_name": "supportflow.refiner-node",
                    "tags": ["supportflow", "agent:refiner"],
                }
            ),
        )
        builder.add_node(
            "finalize",
            RunnableLambda(self.finalize_node).with_config(
                {
                    "run_name": "supportflow.finalizer-node",
                    "tags": ["supportflow", "agent:finalizer"],
                }
            ),
        )

        builder.add_edge(START, "retrieve")
        builder.add_edge("retrieve", "generate")
        builder.add_edge("generate", "validate")
        builder.add_conditional_edges(
            "validate",
            self.route_after_validation,
            {"refine": "refine", "finalize": "finalize"},
        )
        builder.add_edge("refine", "validate")
        builder.add_edge("finalize", END)
        return builder.compile(checkpointer=self.checkpointer)

    def invoke(
        self,
        *,
        thread_id: str,
        input_state: AgentState,
        metadata: dict[str, str],
    ) -> AgentState:
        config = {
            "configurable": {"thread_id": thread_id},
            "run_name": "supportflow.support-request",
            "tags": [
                "supportflow",
                f"agent:{input_state['agent_type']}",
            ],
            "metadata": metadata,
        }
        return self.graph.invoke(input_state, config=config)
