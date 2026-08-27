from routes.auth import router as auth_router
from routes.chat import router as chat_router
from routes.health import router as health_router
from routes.knowledge import router as knowledge_router


__all__ = ["auth_router", "chat_router", "health_router", "knowledge_router"]
