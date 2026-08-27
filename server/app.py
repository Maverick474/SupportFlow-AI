from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from controller.config import get_settings
from controller.resources import close_resources, create_resources
from middleware.request_context import RequestContextMiddleware
from routes import auth_router, chat_router, health_router, knowledge_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.resources = await create_resources(settings)
    try:
        yield
    finally:
        await close_resources(app.state.resources)


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health_router)
    application.include_router(auth_router, prefix=settings.api_prefix)
    application.include_router(chat_router, prefix=settings.api_prefix)
    application.include_router(knowledge_router, prefix=settings.api_prefix)
    return application


app = create_app()
