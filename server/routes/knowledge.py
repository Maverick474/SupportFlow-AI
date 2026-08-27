import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from controller.dependencies import get_resources
from controller.resources import AppResources
from middleware.auth import require_admin
from models.auth import UserPublic
from models.chat import AgentType, KnowledgeIngestRequest, KnowledgeIngestResponse


router = APIRouter(prefix="/knowledge", tags=["knowledge"])
MAX_PDF_BYTES = 20 * 1024 * 1024


@router.post(
    "/upload",
    response_model=KnowledgeIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_knowledge_pdf(
    file: UploadFile = File(...),
    agent_type: AgentType | None = Form(default=None),
    replace_existing: bool = Form(default=True),
    user: UserPublic = Depends(require_admin),
    resources: AppResources = Depends(get_resources),
) -> KnowledgeIngestResponse:
    """Upload and index a PDF for an owner or admin workspace."""
    document_name = Path(file.filename or "knowledge.pdf").name
    if not document_name.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF documents can be uploaded.",
        )

    pdf_bytes = await file.read(MAX_PDF_BYTES + 1)
    await file.close()
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The selected PDF is empty.",
        )
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The PDF must be 20 MB or smaller.",
        )
    if not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The selected file is not a valid PDF.",
        )

    try:
        return await asyncio.to_thread(
            resources.ingestion_service.ingest_uploaded_pdf,
            workspace_id=user.workspace_id,
            document_name=document_name,
            pdf_bytes=pdf_bytes,
            agent_type=agent_type,
            replace_existing=replace_existing,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/ingest-default",
    response_model=KnowledgeIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_default_handbook(
    request: KnowledgeIngestRequest,
    user: UserPublic = Depends(require_admin),
    resources: AppResources = Depends(get_resources),
) -> KnowledgeIngestResponse:
    try:
        return await asyncio.to_thread(
            resources.ingestion_service.ingest_default_handbook,
            workspace_id=user.workspace_id,
            agent_type=request.agent_type,
            replace_existing=request.replace_existing,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
