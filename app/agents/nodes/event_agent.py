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

# Stateless agent — no checkpointer, read-only tools
_agent = create_react_agent(_llm, tools=_TOOLS, max_iterations=5)


async def event_agent_node(state: DeluxeState) -> dict:
    system_prompt = get_system_prompt(state["role"], state["telegram_id"])
    result = await _agent.ainvoke(
        {"messages": state["messages"]},
        config={"configurable": {"system_message": system_prompt}},
    )
    return {"messages": result["messages"]}
