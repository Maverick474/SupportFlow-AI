from dataclasses import dataclass

from pymongo import AsyncMongoClient
from redis import Redis as SyncRedis
from redis.asyncio import Redis
from supabase import Client, create_client

from agents.workflow import SupportFlowWorkflow
from controller.auth_service import AuthService
from controller.chat_service import ChatService
from controller.config import Settings
from controller.conversation_store import ConversationStore
from service.knowledge import AgentRecordRepository, KnowledgeIngestionService
from service.n8n import N8nWebhookClient


@dataclass(slots=True)
class AppResources:
    settings: Settings
    mongo_client: AsyncMongoClient
    redis: Redis
    redis_checkpointer_client: SyncRedis
    supabase: Client
    auth_service: AuthService
    conversation_store: ConversationStore
    agent_repository: AgentRecordRepository
    workflow: SupportFlowWorkflow
    n8n_webhook: N8nWebhookClient
    chat_service: ChatService
    ingestion_service: KnowledgeIngestionService


async def create_resources(settings: Settings) -> AppResources:
    mongo_client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5_000,
    )
    await mongo_client.admin.command("ping")
    mongo_database = mongo_client[settings.mongodb_database]

    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis_client.ping()

    redis_checkpointer_client = SyncRedis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    supabase_client = create_client(settings.supabase_url, settings.supabase_key)
    repository = AgentRecordRepository(supabase_client)
    conversation_store = ConversationStore(redis_client)
    auth_service = AuthService(mongo_database, settings)
    await auth_service.ensure_indexes()

    workflow = SupportFlowWorkflow(
        settings=settings,
        repository=repository,
        redis_client=redis_checkpointer_client,
    )
    n8n_webhook = N8nWebhookClient(
        webhook_url=settings.n8n_webhook_url,
        webhook_secret=settings.n8n_secret,
        timeout_seconds=settings.n8n_timeout_seconds,
    )
    chat_service = ChatService(
        repository=repository,
        conversation_store=conversation_store,
        workflow=workflow,
        n8n_webhook=n8n_webhook,
    )
    ingestion_service = KnowledgeIngestionService(settings, repository)

    return AppResources(
        settings=settings,
        mongo_client=mongo_client,
        redis=redis_client,
        redis_checkpointer_client=redis_checkpointer_client,
        supabase=supabase_client,
        auth_service=auth_service,
        conversation_store=conversation_store,
        agent_repository=repository,
        workflow=workflow,
        n8n_webhook=n8n_webhook,
        chat_service=chat_service,
        ingestion_service=ingestion_service,
    )


async def close_resources(resources: AppResources) -> None:
    await resources.n8n_webhook.aclose()
    await resources.redis.aclose()
    resources.redis_checkpointer_client.close()
    await resources.mongo_client.close()
