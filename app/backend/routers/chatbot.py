"""
Nurse Chatbot API router.

Exposes the LangGraph agent via HTTP endpoints.

Each POST /chat call:
  1. Opens a DB session
  2. Builds MCP tools via PatientToolkit (class-based, session-scoped)
  3. Compiles the LangGraph graph (or reuses a cached graph per session)
  4. Invokes the graph with the nurse's message and session memory
  5. Returns the LLM response and tools used

DELETE /chat/{session_id} clears the in-memory conversation history.
GET    /chat/sessions     lists active session IDs.
"""
from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage

from app import setup_logging
from app.backend.agent.chatbot_graph import ChatbotGraphBuilder
from app.backend.mcp_tools.patient_tools import PatientToolkit
from app.backend.schemas import ChatRequest, ChatResponse

logger = setup_logging()

router = APIRouter(prefix="/chat", tags=["Nurse Chatbot"])

# In-memory set of active session IDs (for the /sessions endpoint).
# MemorySaver already persists messages; this just tracks which sessions exist.
_active_sessions: set = set()


@router.post("", response_model=ChatResponse)
async def nurse_chat(payload: ChatRequest, request: Request):
    """
    Send a nurse message about a specific patient to the LangGraph agent.

    The agent autonomously decides which tools to call (patient profile,
    medical history, recent alerts, knowledge base search) and returns a
    clinically grounded response.

    Args:
        payload: ChatRequest — patient_id, message, session_id
        request: FastAPI request used to access app-level shared state

    Returns:
        ChatResponse — LLM reply, patient_id, session_id, tools_used
    """
    session_factory = request.app.state.session_factory
    rag_service = request.app.state.rag_service

    if session_factory is None:
        raise HTTPException(status_code=503, detail="Database not available")

    tools_used: list[str] = []

    try:
        async with session_factory() as session:
            # Build tools scoped to this DB session
            tools = PatientToolkit(session, rag_service).get_tools()

            # Reuse a compiled graph if the session already exists,
            # otherwise build a new one (MemorySaver is inside the compiled graph)
            graph_cache: dict = request.app.state.chatbot_graphs
            if payload.session_id not in graph_cache:
                graph_cache[payload.session_id] = ChatbotGraphBuilder(tools).build()
                _active_sessions.add(payload.session_id)
                logger.info(
                    f"🆕 New chat session: {payload.session_id} "
                    f"for patient {payload.patient_id}"
                )

            compiled_graph = graph_cache[payload.session_id]

            # Invoke the graph — MemorySaver keyed by thread_id = session_id
            config = {"configurable": {"thread_id": payload.session_id}}
            result = await compiled_graph.ainvoke(
                {
                    "messages": [HumanMessage(content=payload.message)],
                    "patient_id": payload.patient_id,
                    "tools_used": [],
                },
                config=config,
            )

            # Extract the final AI reply
            final_message = result["messages"][-1]
            reply = (
                final_message.content
                if hasattr(final_message, "content")
                else str(final_message)
            )

            # Collect unique tool names called during this turn
            for msg in result["messages"]:
                for tc in getattr(msg, "tool_calls", []):
                    name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    if name and name not in tools_used:
                        tools_used.append(name)

            logger.info(
                f"✅ Chat response | patient={payload.patient_id} "
                f"session={payload.session_id} tools={tools_used or 'none'}"
            )

            return ChatResponse(
                reply=reply,
                patient_id=payload.patient_id,
                session_id=payload.session_id,
                tools_used=tools_used if tools_used else None,
            )

    except Exception as exc:
        logger.error(f"Chat error for session {payload.session_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {exc}")


@router.delete("/{session_id}", status_code=204)
async def clear_session(session_id: str, request: Request):
    """
    Clear the conversation history for a session.

    Removes the compiled LangGraph from the cache, which resets the
    MemorySaver checkpointer and erases all conversation history.
    This operation is idempotent — returns 204 whether or not the session existed.
    """
    graph_cache: dict = request.app.state.chatbot_graphs
    if session_id in graph_cache:
        del graph_cache[session_id]
        _active_sessions.discard(session_id)
        logger.info(f"🗑️  Cleared chat session: {session_id}")


@router.get("/sessions")
async def list_active_sessions():
    """List all currently active chat session IDs."""
    return {"active_sessions": list(_active_sessions), "count": len(_active_sessions)}
