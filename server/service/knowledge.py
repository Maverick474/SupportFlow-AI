"""Knowledge ingestion, vector retrieval, and agent-run storage in Supabase."""

import re
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langsmith import traceable
from supabase import Client

from controller.config import Settings
from models.agent import AgentConfig
from models.chat import AgentType, KnowledgeIngestResponse, Visibility


GENERATOR_MODEL = "openai/gpt-4o-mini"
VALIDATOR_MODEL = "openai/gpt-4.1-mini"
DEFAULT_HANDBOOK = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "SupportFlow_Cloud_Knowledge_Handbook_v2.0_Expanded.pdf"
)


def create_embedding_model(settings: Settings) -> OpenAIEmbeddings:
    """Create the notebook's OpenRouter embedding client."""
    return OpenAIEmbeddings(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )


def normalize_openrouter_model(model: str, fallback: str) -> str:
    selected = (model or fallback).strip()
    return selected if "/" in selected else f"openai/{selected}"


class AgentRecordRepository:
    """Read and write agents, knowledge chunks, and runs in Supabase."""

    def __init__(self, client: Client) -> None:
        self.client = client

    def get_agent_config(
        self,
        workspace_id: UUID,
        agent_type: AgentType,
    ) -> AgentConfig:
        response = (
            self.client.table("agents")
            .select(
                "id,workspace_id,name,agent_type,description,system_prompt,"
                "generator_model,validator_model"
            )
            .eq("workspace_id", str(workspace_id))
            .eq("agent_type", agent_type)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if not response.data:
            return AgentConfig(
                workspace_id=workspace_id,
                name=f"{agent_type.title()} Support Agent",
                agent_type=agent_type,
                description=f"Handles {agent_type} support questions.",
                generator_model=GENERATOR_MODEL,
                validator_model=VALIDATOR_MODEL,
            )

        row = response.data[0]
        row["generator_model"] = normalize_openrouter_model(
            row.get("generator_model", ""),
            GENERATOR_MODEL,
        )
        row["validator_model"] = normalize_openrouter_model(
            row.get("validator_model", ""),
            VALIDATOR_MODEL,
        )
        return AgentConfig.model_validate(row)

    def similarity_search(
        self,
        *,
        workspace_id: UUID,
        query_embedding: list[float],
        visibility: Visibility,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        response = self.client.rpc(
            "match_agent_records",
            {
                "query_embedding": query_embedding,
                "match_workspace_id": str(workspace_id),
                "match_visibility": visibility,
                "match_count": limit,
            },
        ).execute()
        return list(response.data or [])

    def delete_document_knowledge(
        self,
        *,
        workspace_id: UUID,
        document_name: str,
    ) -> None:
        (
            self.client.table("agent_records")
            .delete()
            .eq("workspace_id", str(workspace_id))
            .eq("record_type", "knowledge")
            .contains("data", {"document": document_name})
            .execute()
        )

    def insert_knowledge(self, rows: list[dict[str, Any]]) -> None:
        for start in range(0, len(rows), 50):
            self.client.table("agent_records").insert(
                rows[start : start + 50]
            ).execute()

    def record_run(
        self,
        *,
        workspace_id: UUID,
        agent: AgentConfig,
        mongo_user_id: str,
        conversation_id: UUID,
        ticket_id: UUID | None,
        question: str,
        result: dict[str, Any],
    ) -> UUID:
        run_id = uuid4()
        validation = result["validation"]
        draft = result.get("draft")
        data = {
            "agent_type": agent.agent_type,
            "generator_model_used": agent.generator_model,
            "validator_model_used": agent.validator_model,
            "generated_answer": draft.answer if draft else None,
            "validator_feedback": validation.feedback,
            "validation_status": validation.verdict,
            "final_answer": result["final_answer"],
            "citations": draft.citations if draft else [],
            "retrieved_chunk_ids": result.get("retrieved_chunk_ids", []),
            "revision_count": result.get("revision_count", 0),
        }
        self.client.table("agent_records").insert(
            {
                "id": str(run_id),
                "workspace_id": str(workspace_id),
                "agent_id": str(agent.id) if agent.id else None,
                "record_type": "run",
                "mongo_user_id": mongo_user_id,
                "conversation_id": str(conversation_id),
                "ticket_id": str(ticket_id) if ticket_id else None,
                "content": question,
                "embedding": None,
                "data": data,
            }
        ).execute()
        return run_id


class KnowledgeIngestionService:
    """Load, chunk, embed, and save the project PDF in Supabase."""

    def __init__(
        self,
        settings: Settings,
        repository: AgentRecordRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.embedding_model = create_embedding_model(settings)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1_800,
            chunk_overlap=200,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    @staticmethod
    def _section_title(text: str) -> str:
        for line in text.splitlines():
            candidate = re.sub(r"\s+", " ", line).strip(" -:#")
            candidate = candidate.replace("[", "(").replace("]", ")")
            if candidate and not candidate.isdigit():
                return candidate[:160]
        return "SupportFlow Cloud Knowledge Handbook"

    @traceable(name="supportflow.knowledge-ingestion", run_type="chain")
    def ingest_default_handbook(
        self,
        *,
        workspace_id: UUID,
        agent_type: AgentType | None,
        replace_existing: bool,
    ) -> KnowledgeIngestResponse:
        if not DEFAULT_HANDBOOK.is_file():
            raise FileNotFoundError(
                f"Knowledge handbook was not found at {DEFAULT_HANDBOOK}."
            )

        return self._ingest_pdf(
            pdf_path=DEFAULT_HANDBOOK,
            document_name=DEFAULT_HANDBOOK.name,
            workspace_id=workspace_id,
            agent_type=agent_type,
            replace_existing=replace_existing,
        )

    @traceable(name="supportflow.knowledge-upload", run_type="chain")
    def ingest_uploaded_pdf(
        self,
        *,
        workspace_id: UUID,
        document_name: str,
        pdf_bytes: bytes,
        agent_type: AgentType | None,
        replace_existing: bool,
    ) -> KnowledgeIngestResponse:
        """Ingest a PDF uploaded by an authenticated workspace member."""
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
                temp_file.write(pdf_bytes)
                temporary_path = Path(temp_file.name)

            return self._ingest_pdf(
                pdf_path=temporary_path,
                document_name=document_name,
                workspace_id=workspace_id,
                agent_type=agent_type,
                replace_existing=replace_existing,
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _ingest_pdf(
        self,
        *,
        pdf_path: Path,
        document_name: str,
        workspace_id: UUID,
        agent_type: AgentType | None,
        replace_existing: bool,
    ) -> KnowledgeIngestResponse:
        try:
            pages = PyPDFLoader(str(pdf_path)).load()
        except Exception as exc:
            raise ValueError(
                "The uploaded file could not be read as a PDF."
            ) from exc

        if not pages:
            raise ValueError("The PDF does not contain any readable pages.")

        for page_number, page in enumerate(pages, start=1):
            page.metadata.update(
                {
                    "document": document_name,
                    "page_number": page_number,
                    "section_title": self._section_title(page.page_content),
                    "visibility": "public",
                }
            )

        chunks = self.splitter.split_documents(pages)
        if not chunks:
            raise ValueError("The handbook did not produce any text chunks.")

        embeddings = self.embedding_model.embed_documents(
            [chunk.page_content for chunk in chunks]
        )

        if replace_existing:
            self.repository.delete_document_knowledge(
                workspace_id=workspace_id,
                document_name=document_name,
            )
        agent = (
            self.repository.get_agent_config(workspace_id, agent_type)
            if agent_type is not None
            else None
        )
        rows: list[dict[str, Any]] = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            metadata = dict(chunk.metadata)
            metadata["agent_type"] = agent_type
            rows.append(
                {
                    "workspace_id": str(workspace_id),
                    "agent_id": str(agent.id) if agent and agent.id else None,
                    "record_type": "knowledge",
                    "content": chunk.page_content,
                    "embedding": embedding,
                    "data": metadata,
                }
            )
        self.repository.insert_knowledge(rows)

        return KnowledgeIngestResponse(
            document=document_name,
            pages=len(pages),
            chunks=len(chunks),
            vector_dimensions=self.settings.embedding_dimensions,
        )
