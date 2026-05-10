from langchain_core.messages import SystemMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.prebuilt import create_react_agent

from app.agents.state import DeluxeState
from app.agents.tools.event_tools import ver_detalle_evento, ver_eventos_disponibles
from app.agents.tools.user_tools import registrar_usuario
from app.config import settings
from app.llm.prompts import get_system_prompt

_TOOLS = [ver_eventos_disponibles, ver_detalle_evento, registrar_usuario]

_llm = ChatNVIDIA(
    model=settings.NVIDIA_MODEL_PRIMARY,
    api_key=settings.NVIDIA_API_KEY,
).with_fallbacks(
    [ChatNVIDIA(model=settings.NVIDIA_MODEL_FALLBACK, api_key=settings.NVIDIA_API_KEY)]
)

_agent = create_react_agent(_llm, tools=_TOOLS)


async def event_agent_node(state: DeluxeState) -> dict:
    system_prompt = get_system_prompt(state["role"], state["telegram_id"])
    input_messages = [SystemMessage(content=system_prompt)] + list(state["messages"])
    result = await _agent.ainvoke({"messages": input_messages})
    new_messages = result["messages"][len(input_messages) :]
    return {"messages": new_messages}
