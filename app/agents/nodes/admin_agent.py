from langgraph.prebuilt import create_react_agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from app.agents.state import DeluxeState
from app.agents.tools.admin_tools import (
    admin_crear_evento,
    admin_cambiar_estado_evento,
    admin_cancelar_evento,
    admin_aprobar_orden,
    admin_ver_ordenes_pendientes,
    admin_crear_lote_mesas,
    admin_configurar_precio_mesa,
    admin_crear_tickets_evento,
)
from app.llm.prompts import get_system_prompt
from app.config import settings

_TOOLS = [
    admin_crear_evento,
    admin_cambiar_estado_evento,
    admin_cancelar_evento,
    admin_aprobar_orden,
    admin_ver_ordenes_pendientes,
    admin_crear_lote_mesas,
    admin_configurar_precio_mesa,
    admin_crear_tickets_evento,
]

_llm = ChatNVIDIA(
    model=settings.NVIDIA_MODEL_PRIMARY,
    api_key=settings.NVIDIA_API_KEY,
).with_fallbacks([
    ChatNVIDIA(model=settings.NVIDIA_MODEL_FALLBACK, api_key=settings.NVIDIA_API_KEY)
])

_agent = create_react_agent(_llm, tools=_TOOLS, max_iterations=5)


async def admin_agent_node(state: DeluxeState) -> dict:
    system_prompt = get_system_prompt(state["role"], state["telegram_id"])
    result = await _agent.ainvoke(
        {"messages": state["messages"]},
        config={"configurable": {"system_message": system_prompt}},
    )
    return {"messages": result["messages"]}
