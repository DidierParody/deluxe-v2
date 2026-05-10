from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class DeluxeState(TypedDict):
    messages: Annotated[list, add_messages]
    telegram_id: int
    chat_id: int
    role: str                      # "customer" | "admin"
    next_agent: Optional[str]      # set by router, consumed by conditional edge
    active_flow: Optional[str]     # "event" | "reservation" | "tickets" | "payment" | "admin" | "general"
    event_name: Optional[str]
    party_size: Optional[int]
    selected_table: Optional[int]
    ticket_type: Optional[str]
    quantity: Optional[int]
    update_id: int
