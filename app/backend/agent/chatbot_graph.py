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

Usage:
    compiled_graph = ChatbotGraphBuilder(tools).build()
"""
from typing import Annotated, List

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from app import setup_logging
from app.utils.config import LLM_MODEL, OLLAMA_HOST

logger = setup_logging()


# ---------------------------------------------------------------------------
# Agent state — flows through every LangGraph node
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """
    Shared state that flows through LangGraph nodes.

    Attributes:
        messages:   Full conversation history (Human/AI/Tool messages).
                    The `add_messages` reducer *appends* new messages instead
                    of replacing the list, preserving conversation history.
        patient_id: The patient this conversation is about.
        tools_used: Tool names called in this turn (for UI transparency).
    """

    messages: Annotated[List[BaseMessage], add_messages]
    patient_id: str
    tools_used: List[str]


# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Graph builder — use instead of the old build_chatbot_graph() free function
# ---------------------------------------------------------------------------

class ChatbotGraphBuilder:
    """
    Builds and compiles the LangGraph chatbot graph.

    Encapsulates LLM initialisation, node definitions, and graph wiring
    so the logic is testable and reusable without relying on nested functions.

    Example:
        compiled = ChatbotGraphBuilder(tools).build()
    """

    # Model configuration — override via environment variables
    _LLM_MODEL: str = LLM_MODEL
    _OLLAMA_HOST: str = OLLAMA_HOST

    def __init__(self, tools: list) -> None:
        """
        Args:
            tools: List of @tool-decorated async functions provided by PatientToolkit.
        """
        self._tools = tools
        # Bind tools to ChatOllama — ChatOllama supports tool-calling; OllamaLLM does not
        self._llm = ChatOllama(
            model=self._LLM_MODEL,
            base_url=self._OLLAMA_HOST,
            temperature=0.1,
            num_predict=512,
        ).bind_tools(tools)

    # ── LangGraph nodes ──────────────────────────────────────────────────

    def _llm_node(self, state: AgentState) -> dict:
        """
        Core LLM reasoning node.

        Prepends a patient-anchored system prompt to the conversation
        history, invokes the LLM, and returns the AI response message.
        """
        patient_id = state["patient_id"]
        system_msg = SystemMessage(
            content=NURSE_SYSTEM_PROMPT.format(patient_id=patient_id)
        )
        conversation = state["messages"]
        # Only prepend system message if it is not already the first message
        if not conversation or not isinstance(conversation[0], SystemMessage):
            conversation = [system_msg] + list(conversation)

        response = self._llm.invoke(conversation)
        logger.debug(
            f"LLM response for patient {patient_id}: {str(response.content)[:100]}..."
        )
        return {"messages": [response]}

    def _route_after_llm(self, state: AgentState) -> str:
        """
        Conditional edge: route to tool_executor if the LLM issued tool calls,
        otherwise end the turn.
        """
        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", [])
        if tool_calls:
            tool_names = [tc["name"] for tc in tool_calls]
            logger.info(f"🔧 Tools called: {tool_names}")
            return "tool_executor"
        return END

    # ── Public build method ──────────────────────────────────────────────

    def build(self):
        """
        Compile and return the LangGraph app with MemorySaver checkpointer.

        Returns:
            CompiledGraph: Ready-to-invoke graph with in-memory conversation history.
        """
        tool_node = ToolNode(self._tools)

        graph = StateGraph(AgentState)
        # Wrap bound methods in plain lambdas — LangGraph's node type expects
        # a plain callable, not a bound method reference.
        graph.add_node("llm_node", lambda state: self._llm_node(state))  # type: ignore[arg-type]
        graph.add_node("tool_executor", tool_node)
        graph.add_edge(START, "llm_node")
        graph.add_conditional_edges(
            "llm_node",
            lambda state: self._route_after_llm(state),  # type: ignore[arg-type]
            {"tool_executor": "tool_executor", END: END},
        )
        # After tools execute, feed results back to the LLM for the next turn
        graph.add_edge("tool_executor", "llm_node")

        memory = MemorySaver()
        compiled = graph.compile(checkpointer=memory)
        logger.info(f"✅ Chatbot LangGraph compiled — model: {self._LLM_MODEL}")
        return compiled
