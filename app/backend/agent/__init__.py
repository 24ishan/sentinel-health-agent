"""
Agent package.

Exposes ChatbotGraphBuilder — the class that compiles the LangGraph
nurse chatbot graph.  Build and compile with:

    from app.backend.agent.chatbot_graph import ChatbotGraphBuilder
    compiled = ChatbotGraphBuilder(tools).build()
"""
from app.backend.agent.chatbot_graph import ChatbotGraphBuilder

__all__ = ["ChatbotGraphBuilder"]

