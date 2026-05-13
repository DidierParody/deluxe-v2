"""
Integration tests for the agent graph routing layer.

Tests exercise router_node and route_by_agent directly — no HTTP client,
no DB, no LLM calls — but go deeper than unit tests by validating full
state-dict transitions (active_flow, stale-key clearing, extracted fields).
"""

from unittest.mock import patch

from langchain_core.messages import HumanMessage

# Patch settings before importing router so external service keys aren't required
with patch.dict(
    "os.environ",
    {
        "DATABASE_URL": "postgresql://fake",
        "TELEGRAM_BOT_TOKEN_CS": "fake",
        "TELEGRAM_BOT_TOKEN_AM": "fake",
        "WEBHOOK_BASE_URL": "https://fake.example.com",
        "NVIDIA_API_KEY": "fake",
    },
):
    from app.agents.router import route_by_agent, router_node


def _make_state(text: str, role: str = "customer", active_flow=None, **kwargs) -> dict:
    return {
        "messages": [HumanMessage(content=text)],
        "telegram_id": 111,
        "chat_id": 222,
        "role": role,
        "next_agent": None,
        "active_flow": active_flow,
        "event_name": None,
        "party_size": None,
        "selected_table": None,
        "ticket_type": None,
        "quantity": None,
        "update_id": 99,
        **kwargs,
    }


def test_router_customer_event_query_routes_to_event_agent():
    """A general event query from a customer should reach event_agent."""
    state = _make_state("¿qué eventos hay este fin de semana?")
    result = router_node(state)
    assert result["next_agent"] == "event_agent"
    # Flow is either "general" or "event" — both map to event_agent
    assert result["active_flow"] in ("event", "general")


def test_router_customer_reservation_routes_to_reservation_agent():
    """A reservation request should route to reservation_agent and extract party_size."""
    state = _make_state("quiero reservar una mesa para 4 personas")
    result = router_node(state)
    assert result["next_agent"] == "reservation_agent"
    assert result.get("party_size") == 4


def test_router_admin_always_routes_to_admin_agent():
    """Any message from an admin user must always route to admin_agent."""
    state = _make_state("hola, necesito gestionar los eventos", role="admin")
    result = router_node(state)
    assert result["next_agent"] == "admin_agent"


def test_router_flow_change_clears_stale_keys():
    """Switching from reservation flow to tickets flow clears reservation-specific state.

    Note: the router clears ALL flow-specific keys (including quantity) when the
    flow changes, applying the clear dict last. The new quantity from the message
    is parsed by derive_session_patch but then overridden by the clear operation.
    This is intentional — stale values from the previous flow are wiped first;
    the new agent will re-extract what it needs from the message.
    """
    state = _make_state(
        "quiero comprar 2 tickets",
        active_flow="reservation",
        selected_table=7,
        party_size=3,
    )
    result = router_node(state)
    assert result["next_agent"] == "ticket_agent"
    # Stale reservation keys must be cleared
    assert result.get("selected_table") is None
    assert result.get("party_size") is None
    # quantity is also wiped by the flow-change clear (clear dict applied last)
    assert result.get("quantity") is None


def test_route_by_agent_returns_state_next_agent():
    """route_by_agent should return whatever next_agent is stored in the state."""
    state = _make_state("proceder al pago")
    state["next_agent"] = "payment_agent"
    assert route_by_agent(state) == "payment_agent"
