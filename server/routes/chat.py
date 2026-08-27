from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from controller.conversation_store import ConversationOwnershipError
from controller.dependencies import get_resources
from controller.resources import AppResources
from middleware.auth import get_current_user
from models.auth import UserPublic
from models.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConversationRenameRequest,
    ConversationSummary,
)


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: UserPublic = Depends(get_current_user),
    resources: AppResources = Depends(get_resources),
) -> ChatResponse:
    try:
        return await resources.chat_service.ask(user=user, request=request)
    except ConversationOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/conversations",
    response_model=list[ConversationSummary],
)
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    user: UserPublic = Depends(get_current_user),
    resources: AppResources = Depends(get_resources),
) -> list[ConversationSummary]:
    return await resources.conversation_store.list_conversations(
        mongo_user_id=user.id,
        limit=limit,
    )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationSummary,
)
async def rename_conversation(
    conversation_id: UUID,
    request: ConversationRenameRequest,
    user: UserPublic = Depends(get_current_user),
    resources: AppResources = Depends(get_resources),
) -> ConversationSummary:
    try:
        return await resources.conversation_store.rename_conversation(
            mongo_user_id=user.id,
            conversation_id=conversation_id,
            title=request.title,
        )
    except ConversationOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: UUID,
    user: UserPublic = Depends(get_current_user),
    resources: AppResources = Depends(get_resources),
) -> None:
    try:
        await resources.conversation_store.delete_conversation(
            mongo_user_id=user.id,
            conversation_id=conversation_id,
        )
    except ConversationOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[ChatMessage],
)
async def get_conversation_messages(
    conversation_id: UUID,
    limit: int = Query(default=200, ge=1, le=1_000),
    user: UserPublic = Depends(get_current_user),
    resources: AppResources = Depends(get_resources),
) -> list[ChatMessage]:
    try:
        return await resources.conversation_store.get_messages(
            mongo_user_id=user.id,
            conversation_id=conversation_id,
            limit=limit,
        )
    except ConversationOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
