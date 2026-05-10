import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.nodes.admin_agent import admin_agent_node
from app.agents.nodes.event_agent import event_agent_node
from app.agents.nodes.payment_agent import payment_agent_node
from app.agents.nodes.reservation_agent import reservation_agent_node
from app.agents.nodes.ticket_agent import ticket_agent_node
from app.agents.router import route_by_agent, router_node
from app.agents.state import DeluxeState

logger = logging.getLogger(__name__)

_AGENT_NODES = {
    "event_agent": event_agent_node,
    "reservation_agent": reservation_agent_node,
    "ticket_agent": ticket_agent_node,
    "payment_agent": payment_agent_node,
    "admin_agent": admin_agent_node,
}


def compile_graph(redis_client=None):
    """
    Builds and compiles the LangGraph StateGraph.
    Uses in-process MemorySaver for checkpointing (sufficient for single-task ECS).
    Conversation session context is persisted separately via the Redis session store.
    """
    checkpointer = MemorySaver()

    builder = StateGraph(DeluxeState)
    builder.add_node("router", router_node)

    for name, fn in _AGENT_NODES.items():
        builder.add_node(name, fn)

    builder.set_entry_point("router")
    builder.add_conditional_edges(
        "router",
        route_by_agent,
        {name: name for name in _AGENT_NODES},
    )

    for name in _AGENT_NODES:
        builder.add_edge(name, END)

    return builder.compile(checkpointer=checkpointer)
