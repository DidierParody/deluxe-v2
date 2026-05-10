from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.prebuilt import create_react_agent

from app.agents.state import DeluxeState
from app.agents.tools.event_tools import ver_eventos_disponibles
from app.agents.tools.payment_tools import ver_metodos_de_pago
from app.agents.tools.reservation_tools import (
    cancelar_mi_reserva,
    reservar_mesa,
    ver_mesas_disponibles,
)
from app.config import settings
from app.llm.prompts import get_system_prompt

_TOOLS = [
    ver_mesas_disponibles,
    reservar_mesa,
    cancelar_mi_reserva,
    ver_eventos_disponibles,
    ver_metodos_de_pago,
]

_llm = ChatNVIDIA(
    model=settings.NVIDIA_MODEL_PRIMARY,
    api_key=settings.NVIDIA_API_KEY,
).with_fallbacks(
    [ChatNVIDIA(model=settings.NVIDIA_MODEL_FALLBACK, api_key=settings.NVIDIA_API_KEY)]
)

_agent = create_react_agent(_llm, tools=_TOOLS)


async def reservation_agent_node(state: DeluxeState) -> dict:
    system_prompt = get_system_prompt(state["role"], state["telegram_id"])
    result = await _agent.ainvoke(
        {"messages": state["messages"]},
        config={"configurable": {"system_message": system_prompt}},
    )
    return {"messages": result["messages"]}
