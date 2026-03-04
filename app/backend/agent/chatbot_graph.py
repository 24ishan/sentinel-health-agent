"""
LangGraph-powered Nurse Chatbot Agent.
Architecture:
    START
      └─▶ llm_node  (ChatOllama bound with MCP tools)
              │
              ├─▶ [has tool calls] ─▶ tool_executor (ToolNode)
              │                              └─▶ llm_node  (loop)
              │
              └─▶ [no tool calls]  ─▶ END
The agent uses MemorySaver as a checkpointer so each nurse session
retains conversation history across multiple messages (thread_id = session_id).
MCP Tool Pattern:
    Tools are registered via @tool decorator from langchain_core.
    The LLM autonomously decides which tools to call.
    The ToolNode executes them and feeds results back to the LLM.
    This mirrors the Model Context Protocol (MCP) pattern.
"""
from typing import Annotated, List
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from app import setup_logging
from app.utils.config import LLM_MODEL, OLLAMA_HOST
logger = setup_logging()
# ─────────────────────────────────────────────
# Agent State
# ─────────────────────────────────────────────
class AgentState(TypedDict):
    """
    State that flows through the LangGraph nodes.
    messages: Full conversation history (HumanMessage, AIMessage, ToolMessage).
              add_messages reducer appends new messages instead of replacing.
    patient_id: The patient this conversation is about.
    tools_used: Accumulates names of tools called in this turn (for UI transparency).
    """
    messages: Annotated[List[BaseMessage], add_messages]
    patient_id: str
    tools_used: List[str]
# ─────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────
NURSE_SYSTEM_PROMPT = """You are a clinical AI assistant helping nurses at a hospital.
You are currently consulted about patient {patient_id}.
Your responsibilities:
- Answer clinical questions about this specific patient using available tools
- Retrieve patient profile, medical history, and recent alerts when relevant
- Search the medical knowledge base for evidence-based clinical guidelines
- Provide clear, concise, medically appropriate responses
- Always flag critical information (allergies, dangerous drug interactions)
- Remind the nurse to use professional clinical judgment alongside your advice
Available tools:
- get_patient_profile: Patient demographics and contact info
- get_medical_history: Allergies, medications, conditions, history
- get_recent_alerts: Recent vital sign alerts and AI advice
- search_medical_knowledge: Clinical guidelines from the knowledge base
Always be helpful, accurate, and safety-conscious.
If you are unsure, say so clearly and recommend consulting a physician."""
# ─────────────────────────────────────────────
# Graph Builder
# ─────────────────────────────────────────────
def build_chatbot_graph(tools: list):
    """
    Compile the LangGraph chatbot graph with the given tool list.
    Args:
        tools: List of @tool-decorated functions from build_patient_tools()
    Returns:
        Compiled LangGraph app with MemorySaver checkpointer
    """
    # Bind tools to ChatOllama for tool-calling support
    # ChatOllama supports tool calling; OllamaLLM does not
    llm = ChatOllama(
        model=LLM_MODEL,
        base_url=OLLAMA_HOST,
        temperature=0.1,
        num_predict=512,
    ).bind_tools(tools)
    # ── Node: LLM reasoning ──────────────────
    def llm_node(state: AgentState) -> dict:
        """
        Core LLM node. Prepends a system prompt anchored to the patient context.
        Returns updated messages (AIMessage with optional tool_calls).
        """
        patient_id = state["patient_id"]
        system_msg = SystemMessage(
            content=NURSE_SYSTEM_PROMPT.format(patient_id=patient_id)
        )
        # Prepend system message (only if not already first message)
        conversation = state["messages"]
        if not conversation or not isinstance(conversation[0], SystemMessage):
            conversation = [system_msg] + conversation
        response = llm.invoke(conversation)
        logger.debug(f"LLM response for patient {patient_id}: {response.content[:100]}...")
        return {"messages": [response]}
    # ── Node: Tool executor ──────────────────
    tool_node = ToolNode(tools)
    # ── Conditional edge router ──────────────
    def route_after_llm(state: AgentState) -> str:
        """
        Decide next step after LLM:
          - If the LLM wants to call a tool → go to tool_executor
          - Otherwise → END
        """
        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", [])
        if tool_calls:
            # Track which tools are being used for UI transparency
            tool_names = [tc["name"] for tc in tool_calls]
            logger.info(f"🔧 Tools called: {tool_names}")
            return "tool_executor"
        return END
    # ── Build the graph ──────────────────────
    graph = StateGraph(AgentState)
    graph.add_node("llm_node", llm_node)
    graph.add_node("tool_executor", tool_node)
    graph.add_edge(START, "llm_node")
    graph.add_conditional_edges(
        "llm_node",
        route_after_llm,
        {"tool_executor": "tool_executor", END: END},
    )
    graph.add_edge("tool_executor", "llm_node")   # Loop back after tool execution
    # ── Compile with memory checkpointer ────
    memory = MemorySaver()
    compiled = graph.compile(checkpointer=memory)
    logger.info(f"✅ Chatbot LangGraph compiled — model: {LLM_MODEL}")
    return compiled
