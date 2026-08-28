import asyncio
from uuid import UUID, uuid4

from agents.routing import route_agent_type
from agents.workflow import SupportFlowWorkflow
from controller.conversation_store import ConversationStore
from models.agent import AgentState
from models.auth import UserPublic
from models.chat import ChatRequest, ChatResponse
from service.knowledge import AgentRecordRepository
from service.n8n import N8nWebhookClient


class ChatService:
    def __init__(
        self,
        *,
        repository: AgentRecordRepository,
        conversation_store: ConversationStore,
        workflow: SupportFlowWorkflow,
        n8n_webhook: N8nWebhookClient,
    ) -> None:
        self.repository = repository
        self.conversation_store = conversation_store
        self.workflow = workflow
        self.n8n_webhook = n8n_webhook

    async def ask(
        self,
        *,
        user: UserPublic,
        request: ChatRequest,
    ) -> ChatResponse:
        conversation_id = request.conversation_id or uuid4()
        agent_type = route_agent_type(
            request.question,
            request.agent_type,
        )
        if (
            request.conversation_id is not None
            and request.agent_type is None
            and agent_type == "general"
        ):
            previous_agent_type = await self.conversation_store.get_agent_type(
                mongo_user_id=user.id,
                conversation_id=conversation_id,
            )
            if previous_agent_type is not None:
                agent_type = previous_agent_type

        await self.conversation_store.ensure_conversation(
            mongo_user_id=user.id,
            conversation_id=conversation_id,
            agent_type=agent_type,
            first_question=request.question,
        )
        await self.conversation_store.append_message(
            conversation_id=conversation_id,
            role="user",
            content=request.question,
        )

        agent = await asyncio.to_thread(
            self.repository.get_agent_config,
            user.workspace_id,
            agent_type,
        )
        input_state: AgentState = {
            "question": request.question,
            "workspace_id": str(user.workspace_id),
            "agent_type": agent_type,
            "agent_name": agent.name,
            "agent_system_prompt": agent.system_prompt,
            "generator_model": agent.generator_model,
            "validator_model": agent.validator_model,
            "user_visibility": request.user_visibility,
        }
        result = await asyncio.to_thread(
            self.workflow.invoke,
            thread_id=f"{user.id}:{conversation_id}",
            input_state=input_state,
            metadata={
                "workspace_id": str(user.workspace_id),
                "conversation_id": str(conversation_id),
                "agent_type": agent_type,
            },
        )

        draft = result.get("draft")
        citations = (
            draft.citations
            if draft and result["validation"].verdict == "pass"
            else []
        )
        await self.conversation_store.append_message(
            conversation_id=conversation_id,
            role="assistant",
            content=result["final_answer"],
            agent_type=agent_type,
            verdict=result["validation"].verdict,
            citations=citations,
        )

        run_id = await asyncio.to_thread(
            self.repository.record_run,
            workspace_id=user.workspace_id,
            agent=agent,
            mongo_user_id=user.id,
            conversation_id=conversation_id,
            ticket_id=request.ticket_id,
            question=request.question,
            result=result,
        )
        validation = result["validation"]
        self.n8n_webhook.dispatch(
            {
                "event_type": "agent_run_completed",
                "run_id": str(run_id),
                "agent_type": agent_type,
                "validation_status": validation.verdict,
                "requires_human_review": validation.verdict == "escalate",
            }
        )
        return ChatResponse(
            conversation_id=conversation_id,
            run_id=run_id,
            agent_type=agent_type,
            verdict=result["validation"].verdict,
            final_answer=result["final_answer"],
            citations=citations,
            revision_count=result.get("revision_count", 0),
        )
