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
from vector.embeddings import create_embedding_model
from vector.repository import AgentRecordRepository


def format_conversation_history(state: AgentState, limit: int = 2) -> str:
    turns = state.get("conversation_history", [])[-limit:]
    if not turns:
        return "(no earlier turns)"

    formatted_turns: list[str] = []
    for turn in turns:
        formatted_turns.append(f"User: {turn['question']}")
        if turn.get("verdict") == "pass":
            formatted_turns.append(f"Assistant: {turn['answer']}")
    return "\n".join(formatted_turns)


def previous_user_question(state: AgentState) -> str:
    turns = state.get("conversation_history", [])
    return turns[-1]["question"] if turns else ""


def normalize_evidence_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def passages_by_source(evidence: str) -> dict[str, list[str]]:
    passages: dict[str, list[str]] = {}
    pattern = r"\[Source: ([^\]]+)\]\n(.*?)(?=\n\n\[Source: |\Z)"
    for match in re.finditer(pattern, evidence, flags=re.DOTALL):
        label, passage = match.groups()
        passages.setdefault(label, []).append(normalize_evidence_text(passage))
    return passages


def audit_quote_matches_source(
    audit: ClaimAudit,
    source_passages: dict[str, list[str]],
) -> bool:
    quote = normalize_evidence_text(audit.evidence_quote)
    if not quote:
        return False
    return any(
        quote in passage
        for passage in source_passages.get(audit.source_label, [])
    )


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
            max_completion_tokens=1_000,
        )
        validator_llm = ChatOpenAI(
            base_url=self.settings.openrouter_base_url,
            api_key=self.settings.openrouter_key,
            model=validator_model,
            temperature=0.0,
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
        prior_question = previous_user_question(state)
        retrieval_query = state["question"]
        if prior_question:
            retrieval_query = (
                f"Previous user question: {prior_question}\n"
                f"Current follow-up question: {state['question']}"
            )

        query_embedding = self.embedding_model.embed_query(retrieval_query)
        selected = self.repository.similarity_search(
            workspace_id=UUID(state["workspace_id"]),
            query_embedding=query_embedding,
            visibility=visibility,
            limit=5,
        )

        passages: list[str] = []
        chunk_ids: list[str] = []
        for chunk in selected:
            metadata = chunk.get("metadata") or {}
            label = (
                f"Handbook v2.0, p. {metadata.get('page_number', '?')}, "
                f"{metadata.get('section_title', 'Unknown section')}"
            )
            passages.append(f"[Source: {label}]\n{chunk['content']}")
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
        draft = generator_chain.invoke(
            {
                "question": state["question"],
                "history": format_conversation_history(state),
                "evidence": "\n\n".join(state["retrieved_passages"]),
                "agent_name": state["agent_name"],
                "agent_type": state["agent_type"],
                "agent_system_prompt": state.get("agent_system_prompt", ""),
            }
        )
        return {"draft": draft}

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
                "evidence": evidence,
                "draft": state["draft"].model_dump_json(indent=2),
            }
        )

        evidence_labels = set(re.findall(r"\[Source: ([^\]]+)\]", evidence))
        declared_citations = state["draft"].citations
        inline_citations = re.findall(
            r"\[(Handbook v2\.0, p\. \d+, [^\]]+)\]",
            state["draft"].answer,
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
                problems.append(
                    f"remove citations not present in evidence: {invalid_citations}"
                )
            if missing_inline:
                problems.append(
                    f"place these citations in the answer: {missing_inline}"
                )
            if undeclared_inline:
                problems.append(
                    f"declare these inline citations: {undeclared_inline}"
                )
            if not result.claim_audits:
                problems.append("audit every atomic factual claim")
            if failed_audits:
                problems.append(
                    f"remove or correct unsupported claims: {failed_audits}"
                )
            if invalid_audit_sources:
                problems.append(
                    f"use supplied source labels: {invalid_audit_sources}"
                )
            if invalid_audit_quotes:
                problems.append(
                    f"provide exact retrieved evidence: {invalid_audit_quotes}"
                )
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
            and state.get("revision_count", 0) >= 1
        ):
            result = result.model_copy(
                update={
                    "verdict": "escalate",
                    "feedback": (
                        result.feedback
                        + " The single permitted revision was already used."
                    ),
                }
            )
        return {"validation": result}

    def refine_node(self, state: AgentState) -> dict:
        _, _, refiner_chain = self._chains(
            state["generator_model"],
            state["validator_model"],
        )
        revised = refiner_chain.invoke(
            {
                "question": state["question"],
                "history": format_conversation_history(state),
                "evidence": "\n\n".join(state["retrieved_passages"]),
                "draft": state["draft"].model_dump_json(indent=2),
                "feedback": state["validation"].feedback,
            }
        )
        return {
            "draft": revised,
            "revision_count": state.get("revision_count", 0) + 1,
        }

    @staticmethod
    def finalize_node(state: AgentState) -> dict:
        verdict = state["validation"].verdict
        if verdict == "pass":
            final = state["draft"].answer
        elif verdict == "refuse":
            final = (
                "I can't help with that request safely. "
                f"{state['validation'].feedback}"
            )
        else:
            final = (
                "I can't verify or complete this request from handbook "
                "evidence alone. It needs an authorized tool or human review. "
                f"Reason: {state['validation'].feedback}"
            )
        completed_turn = {
            "question": state["question"],
            "answer": final,
            "verdict": verdict,
        }
        return {
            "final_answer": final,
            "conversation_history": [completed_turn],
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
