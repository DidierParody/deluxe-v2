"""
Unit tests for the router node.
No LLM or DB calls — pure Python logic.
"""
import pytest
from langchain_core.messages import HumanMessage
from unittest.mock import patch

# Patch settings before importing router so NVIDIA_API_KEY isn't required
with patch.dict("os.environ", {
    "DATABASE_URL": "postgresql://fake",
    "TELEGRAM_BOT_TOKEN_CS": "fake",
    "TELEGRAM_BOT_TOKEN_AM": "fake",
    "WEBHOOK_BASE_URL": "https://fake.example.com",
    "NVIDIA_API_KEY": "fake",
}):
    from app.agents.router import router_node, route_by_agent


def _make_state(text: str, role: str = "customer", active_flow: str = None) -> dict:
    return {
        "messages": [HumanMessage(content=text)],
        "telegram_id": 123456,
        "chat_id": 789,
        "role": role,
        "next_agent": None,
        "active_flow": active_flow,
        "event_name": None,
        "party_size": None,
        "selected_table": None,
        "ticket_type": None,
        "quantity": None,
        "update_id": 1,
    }


def test_admin_always_routes_to_admin_agent():
    state = _make_state("quiero ver ordenes pendientes", role="admin")
    result = router_node(state)
    assert result["next_agent"] == "admin_agent"


def test_reservation_keywords_route_to_reservation_agent():
    state = _make_state("quiero reservar una mesa vip")
    result = router_node(state)
    assert result["next_agent"] == "reservation_agent"


def test_ticket_keywords_route_to_ticket_agent():
    state = _make_state("necesito 2 tickets para el evento")
    result = router_node(state)
    assert result["next_agent"] == "ticket_agent"


def test_payment_keywords_route_to_payment_agent():
    state = _make_state("ya hice el pago, quiero ver mi comprobante")
    result = router_node(state)
    assert result["next_agent"] == "payment_agent"


def test_general_query_routes_to_event_agent():
    state = _make_state("qué eventos hay disponibles?")
    result = router_node(state)
    assert result["next_agent"] == "event_agent"


def test_flow_change_clears_stale_keys():
    # User was in reservation flow, now asks about tickets
    state = _make_state("quiero comprar entradas", active_flow="reservation")
    state["selected_table"] = 5
    state["party_size"] = 3
    result = router_node(state)
    assert result["next_agent"] == "ticket_agent"
    assert result.get("selected_table") is None
    assert result.get("party_size") is None


def test_route_by_agent_returns_correct_node():
    state = _make_state("hola")
    state["next_agent"] = "ticket_agent"
    assert route_by_agent(state) == "ticket_agent"


def test_route_by_agent_defaults_to_event_agent():
    state = _make_state("hola")
    state["next_agent"] = None
    assert route_by_agent(state) == "event_agent"


def test_party_size_extracted_from_text():
    state = _make_state("somos 4 personas y queremos una mesa")
    result = router_node(state)
    assert result.get("party_size") == 4


def test_quantity_extracted_from_text():
    state = _make_state("quiero 3 tickets generales")
    result = router_node(state)
    assert result.get("quantity") == 3
