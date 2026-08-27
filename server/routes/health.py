from fastapi import APIRouter, Depends

from controller.dependencies import get_resources
from controller.resources import AppResources


router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict[str, str]:
    return {"message": "SupportFlow AI API is running"}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@router.get("/health/ready")
async def readiness(
    resources: AppResources = Depends(get_resources),
) -> dict[str, str]:
    await resources.mongo_client.admin.command("ping")
    await resources.redis.ping()
    return {
        "status": "ready",
        "mongodb": "connected",
        "redis": "connected",
        "supabase": "configured",
        "langsmith_tracing": (
            "enabled" if resources.settings.langsmith_tracing else "disabled"
        ),
    }
