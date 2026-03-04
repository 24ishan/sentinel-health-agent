"""
Nurse Chatbot API router.
Exposes the LangGraph agent via HTTP endpoints.
Each POST /chat call:
  1. Opens a DB session
  2. Builds MCP tools with that session + RAG service
  3. Compiles the LangGraph graph (or reuses compiled graph with new tools)
  4. Invokes the graph with the nurse's message and session memory
  5. Returns the LLM response + tools used
DELETE /chat/{session_id} clears the in-memory conversation history.
"""
from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage
from app import setup_logging
from app.backend.agent.chatbot_graph import build_chatbot_graph
from app.backend.mcp_tools.patient_tools import build_patient_tools
from app.backend.schemas import ChatRequest, ChatResponse
logger = setup_logging()
router = APIRouter(prefix="/chat", tags=["Nurse Chatbot"])
# In-memory session store for MemorySaver thread IDs
# MemorySaver already stores messages; this just tracks active sessions
_active_sessions: set = set()
@router.post("", response_model=ChatResponse)
async def nurse_chat(payload: ChatRequest, request: Request):
    """
    Send a message from a nurse about a specific patient.
    The LangGraph agent will autonomously:
    - Retrieve patient profile and medical history if relevant
    - Look up recent clinical alerts
    - Search the medical knowledge base
    - Generate a clinically grounded response
    Args:
        payload: ChatRequest with patient_id, message, session_id
        request: FastAPI request (used to access app-level rag_service)
    Returns:
        ChatResponse with the LLM reply and tools used
    """
    # Access shared resources from app state
    session_factory = request.app.state.session_factory
    rag_service = request.app.state.rag_service
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Database not available")
    tools_used = []
    try:
        async with session_factory() as session:
            # Build tools with current session (MCP tool injection pattern)
            tools = build_patient_tools(session, rag_service)
            # Build and compile graph
            # Note: MemorySaver is inside the compiled graph — each call to
            # build_chatbot_graph creates a fresh MemorySaver. For persistent
            # memory across requests, the compiled graph must be cached.
            # We store it in app.state keyed by session_id.
            graph_cache = request.app.state.chatbot_graphs
            if payload.session_id not in graph_cache:
                graph_cache[payload.session_id] = build_chatbot_graph(tools)
                _active_sessions.add(payload.session_id)
                logger.info(f"🆕 New chat session: {payload.session_id} for patient {payload.patient_id}")
            compiled_graph = graph_cache[payload.session_id]
            # Invoke the graph with the new message
            config = {"configurable": {"thread_id": payload.session_id}}
            result = await compiled_graph.ainvoke(
                {
                    "messages": [HumanMessage(content=payload.message)],
                    "patient_id": payload.patient_id,
                    "tools_used": [],
                },
                config=config,
            )
            # Extract the final AI response
            final_message = result["messages"][-1]
            reply = final_message.content if hasattr(final_message, "content") else str(final_message)
            # Collect tool names used in this turn
            for msg in result["messages"]:
                tool_calls = getattr(msg, "tool_calls", [])
                for tc in tool_calls:
                    name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    if name and name not in tools_used:
                        tools_used.append(name)
            logger.info(
                f"✅ Chat response for patient {payload.patient_id} "
                f"| Session {payload.session_id} "
                f"| Tools: {tools_used or 'none'}"
            )
            return ChatResponse(
                reply=reply,
                patient_id=payload.patient_id,
                session_id=payload.session_id,
                tools_used=tools_used if tools_used else None,
            )
    except Exception as e:
        logger.error(f"Chat error for session {payload.session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")
@router.delete("/{session_id}", status_code=204)
async def clear_session(session_id: str, request: Request):
    """
    Clear the conversation history for a session.
    This removes the LangGraph compiled graph from cache,
    effectively resetting the nurse's conversation memory.
    """
    graph_cache = request.app.state.chatbot_graphs
    if session_id in graph_cache:
        del graph_cache[session_id]
        _active_sessions.discard(session_id)
        logger.info(f"🗑️  Cleared chat session: {session_id}")
    # Return 204 whether session existed or not (idempotent)
@router.get("/sessions", tags=["Nurse Chatbot"])
async def list_active_sessions():
    """List all currently active chat sessions."""
    return {"active_sessions": list(_active_sessions), "count": len(_active_sessions)}
