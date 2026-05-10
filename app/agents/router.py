from langchain_core.messages import HumanMessage

from app.agents.state import DeluxeState
from app.llm.session_memory import derive_session_patch

# Maps active_flow values to agent node names
_FLOW_TO_AGENT: dict[str, str] = {
    "reservation": "reservation_agent",
    "tickets": "ticket_agent",
    "payment": "payment_agent",
    "admin": "admin_agent",
    "event": "event_agent",
    "general": "event_agent",
}


def router_node(state: DeluxeState) -> dict:
    """
    Pure-Python routing node — zero LLM calls.
    Reads the last human message, derives the active flow, and sets next_agent.
    Also hydrates session fields (event_name, party_size, etc.) from the message.
    """
    if state["role"] == "admin":
        return {"next_agent": "admin_agent"}

    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    text = last_human.content if last_human else ""

    patch = derive_session_patch(state["role"], text)
    active_flow = patch.get("active_flow", state.get("active_flow") or "general")

    # Clear stale flow-specific keys when the flow changes
    current_flow = state.get("active_flow")
    flow_changed = current_flow and current_flow != active_flow
    clear: dict = {}
    if flow_changed:
        clear = {
            "selected_table": None,
            "ticket_type": None,
            "quantity": None,
            "party_size": None,
        }

    return {
        "next_agent": _FLOW_TO_AGENT.get(active_flow, "event_agent"),
        "active_flow": active_flow,
        **{k: v for k, v in patch.items() if k != "active_flow"},
        **clear,
    }


def route_by_agent(state: DeluxeState) -> str:
    """Conditional edge: returns the target node name from state.next_agent."""
    return state.get("next_agent") or "event_agent"
