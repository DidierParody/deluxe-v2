from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class DeluxeState(TypedDict):
    messages: Annotated[list, add_messages]
    telegram_id: int
    chat_id: int
    role: str  # "customer" | "admin"
    next_agent: str | None  # set by router, consumed by conditional edge
    active_flow: str | None  # "event" | "reservation" | "tickets" | "payment" | "admin" | "general"
    event_name: str | None
    party_size: int | None
    selected_table: int | None
    ticket_type: str | None
    quantity: int | None
    update_id: int
