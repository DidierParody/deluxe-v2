from langgraph.prebuilt import create_react_agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from app.agents.state import DeluxeState
from app.agents.tools.ticket_tools import ver_tickets_disponibles, comprar_tickets
from app.agents.tools.event_tools import ver_eventos_disponibles
from app.agents.tools.payment_tools import ver_metodos_de_pago
from app.llm.prompts import get_system_prompt
from app.config import settings

_TOOLS = [ver_tickets_disponibles, comprar_tickets, ver_eventos_disponibles, ver_metodos_de_pago]

_llm = ChatNVIDIA(
    model=settings.NVIDIA_MODEL_PRIMARY,
    api_key=settings.NVIDIA_API_KEY,
).with_fallbacks([
    ChatNVIDIA(model=settings.NVIDIA_MODEL_FALLBACK, api_key=settings.NVIDIA_API_KEY)
])

_agent = create_react_agent(_llm, tools=_TOOLS, max_iterations=5)


async def ticket_agent_node(state: DeluxeState) -> dict:
    system_prompt = get_system_prompt(state["role"], state["telegram_id"])
    result = await _agent.ainvoke(
        {"messages": state["messages"]},
        config={"configurable": {"system_message": system_prompt}},
    )
    return {"messages": result["messages"]}
