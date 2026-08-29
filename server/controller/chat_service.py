import asyncio
from uuid import UUID, uuid4

from agents.routing import route_agent_type, should_create_ticket
from agents.tickets import TicketAgent
from agents.workflow import SupportFlowWorkflow, small_talk_kind
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
        ticket_agent: TicketAgent,
        n8n_webhook: N8nWebhookClient,
    ) -> None:
        self.repository = repository
        self.conversation_store = conversation_store
        self.workflow = workflow
        self.ticket_agent = ticket_agent
        self.n8n_webhook = n8n_webhook

    async def ask(
        self,
        *,
        user: UserPublic,
        request: ChatRequest,
    ) -> ChatResponse:
        conversation_id = request.conversation_id or uuid4()
        interaction_kind = small_talk_kind(request.question)
        agent_type = (
            "general"
            if interaction_kind is not None
            else route_agent_type(request.question, request.agent_type)
        )
        stored_agent_type = agent_type
        if (
            request.conversation_id is not None
            and request.agent_type is None
        ):
            previous_agent_type = await self.conversation_store.get_agent_type(
                mongo_user_id=user.id,
                conversation_id=conversation_id,
            )
            if interaction_kind is not None:
                stored_agent_type = previous_agent_type or "general"
            elif agent_type == "general" and previous_agent_type is not None:
                agent_type = previous_agent_type
                stored_agent_type = previous_agent_type

        await self.conversation_store.ensure_conversation(
            mongo_user_id=user.id,
            conversation_id=conversation_id,
            agent_type=stored_agent_type,
            first_question=request.question,
        )
        conversation_history = []
        if request.conversation_id is not None:
            conversation_history = (
                await self.conversation_store.get_recent_completed_turns(
                    mongo_user_id=user.id,
                    conversation_id=conversation_id,
                    limit=3,
                )
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
            "conversation_history": conversation_history,
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

        validation = result["validation"]
        scope_decision = result.get("scope_decision")
        ticket_request = (
            interaction_kind is None
            and scope_decision is not None
            and scope_decision.classification == "in_scope"
            and validation.verdict != "refuse"
            and should_create_ticket(
                request.question,
                agent_type=agent_type,
                requested_agent=request.agent_type,
            )
        )
        if ticket_request and validation.verdict != "escalate":
            validation = validation.model_copy(
                update={
                    "verdict": "escalate",
                    "feedback": (
                        "The request describes an active support incident or "
                        "explicitly asks for a ticket or live support action."
                    ),
                }
            )
            result["validation"] = validation
        elif validation.verdict == "escalate":
            validation = validation.model_copy(
                update={
                    "verdict": "revise",
                    "feedback": (
                        "The knowledge answer could not be fully verified, but "
                        "the user did not report an active incident or request "
                        "a ticket. Do not create a support ticket automatically."
                    ),
                }
            )
            result["validation"] = validation

        run_id = uuid4()
        created_ticket: dict | None = None
        if ticket_request:
            ticket_config = await asyncio.to_thread(
                self.repository.get_agent_config,
                user.workspace_id,
                "ticket",
            )
            ticket_draft = await asyncio.to_thread(
                self.ticket_agent.create_draft,
                model_name=ticket_config.generator_model,
                source_agent=agent_type,
                question=request.question,
                final_answer=result["final_answer"],
                validator_feedback=validation.feedback,
            )
            ticket_id = uuid4()
            created_ticket = self.repository.build_ticket_data(
                ticket_id=ticket_id,
                run_id=run_id,
                workspace_id=user.workspace_id,
                conversation_id=conversation_id,
                source_agent_type=agent_type,
                requester_name=user.full_name,
                requester_email=str(user.email),
                escalation_reason=validation.feedback,
                draft=ticket_draft,
            )
            result["final_answer"] = (
                "I’ve created a support ticket for authorized human review.\n\n"
                f"Ticket: {created_ticket['ticket_reference']}\n"
                "Status: Open\n"
                f"Priority: {ticket_draft.priority.title()}\n"
                f"Summary: {ticket_draft.title}"
            )

        draft = result.get("draft")
        citations = (
            draft.citations
            if draft and validation.verdict == "pass"
            else []
        )
        await asyncio.to_thread(
            self.repository.record_run,
            workspace_id=user.workspace_id,
            agent=agent,
            mongo_user_id=user.id,
            conversation_id=conversation_id,
            ticket_id=request.ticket_id,
            question=request.question,
            result=result,
            run_id=run_id,
            created_ticket=created_ticket,
        )
        await self.conversation_store.append_message(
            conversation_id=conversation_id,
            role="assistant",
            content=result["final_answer"],
            agent_type=agent_type,
            verdict=validation.verdict,
            citations=citations,
        )
        webhook_agent_type = agent_type
        if webhook_agent_type == "ticket":
            category = (
                created_ticket.get("category") if created_ticket else None
            )
            webhook_agent_type = (
                category
                if category in {"technical", "billing", "account", "policy"}
                else "general"
            )
        webhook_payload = {
            "event_type": "agent_run_completed",
            "run_id": str(run_id),
            "agent_type": webhook_agent_type,
            "validation_status": validation.verdict,
            "requires_human_review": created_ticket is not None,
        }
        if created_ticket is not None:
            webhook_payload.update(created_ticket)
            webhook_payload["handled_by_agent"] = "ticket"
            webhook_payload["source_agent_type"] = agent_type
        await self.n8n_webhook.dispatch(webhook_payload)
        return ChatResponse(
            conversation_id=conversation_id,
            run_id=run_id,
            agent_type=agent_type,
            verdict=validation.verdict,
            final_answer=result["final_answer"],
            citations=citations,
            revision_count=result.get("revision_count", 0),
            ticket_id=(
                UUID(created_ticket["ticket_id"])
                if created_ticket is not None
                else None
            ),
            ticket_reference=(
                created_ticket["ticket_reference"]
                if created_ticket is not None
                else None
            ),
            ticket_status=(
                created_ticket["status"]
                if created_ticket is not None
                else None
            ),
            ticket_priority=(
                created_ticket["priority"]
                if created_ticket is not None
                else None
            ),
        )
