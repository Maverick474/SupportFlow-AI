from fastapi import APIRouter, Depends, HTTPException, status

from controller.auth_service import AuthenticationError, UserAlreadyExistsError
from controller.dependencies import get_resources
from controller.resources import AppResources
from middleware.auth import get_current_user
from models.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserPublic,
)


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    resources: AppResources = Depends(get_resources),
) -> TokenPair:
    try:
        return await resources.auth_service.register(request)
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post("/login", response_model=TokenPair)
async def login(
    request: LoginRequest,
    resources: AppResources = Depends(get_resources),
) -> TokenPair:
    try:
        return await resources.auth_service.login(
            str(request.email),
            request.password,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    request: RefreshRequest,
    resources: AppResources = Depends(get_resources),
) -> TokenPair:
    try:
        return await resources.auth_service.refresh(request.refresh_token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: LogoutRequest,
    _: UserPublic = Depends(get_current_user),
    resources: AppResources = Depends(get_resources),
) -> None:
    await resources.auth_service.logout(request.refresh_token)


@router.get("/me", response_model=UserPublic)
async def me(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return user
