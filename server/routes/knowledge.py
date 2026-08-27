import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from controller.dependencies import get_resources
from controller.resources import AppResources
from middleware.auth import require_admin
from models.auth import UserPublic
from models.chat import KnowledgeIngestRequest, KnowledgeIngestResponse


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


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
