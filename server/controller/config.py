from functools import lru_cache
import os
from uuid import UUID

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(SERVER_DIR, ".env")

# LangSmith reads its settings directly from the process environment.
load_dotenv(ENV_FILE, override=False)


class Settings(BaseSettings):
    app_name: str = "SupportFlow AI API"
    app_env: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173"

    mongodb_uri: str
    mongodb_database: str = "supportflow"
    redis_url: str

    supabase_url: str
    supabase_secret_key: SecretStr = Field(
        validation_alias=AliasChoices(
            "SUPABASE_SECRET_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        )
    )

    openrouter_api_key: SecretStr
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = 384

    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    langsmith_tracing: bool = True
    langsmith_api_key: SecretStr
    langsmith_project: str = "supportflow-ai-development"

    n8n_webhook_url: str = ""
    n8n_webhook_secret: SecretStr | None = None
    n8n_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    default_workspace_id: UUID

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def supabase_key(self) -> str:
        return self.supabase_secret_key.get_secret_value()

    @property
    def openrouter_key(self) -> str:
        return self.openrouter_api_key.get_secret_value()

    @property
    def jwt_key(self) -> str:
        return self.jwt_secret_key.get_secret_value()

    @property
    def n8n_secret(self) -> str | None:
        if self.n8n_webhook_secret is None:
            return None
        return self.n8n_webhook_secret.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
