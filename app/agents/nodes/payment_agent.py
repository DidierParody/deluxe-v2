from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.prebuilt import create_react_agent

from app.agents.state import DeluxeState
from app.agents.tools.payment_tools import ver_metodos_de_pago, ver_mis_ordenes
from app.config import settings
from app.llm.prompts import get_system_prompt

_TOOLS = [ver_mis_ordenes, ver_metodos_de_pago]

_llm = ChatNVIDIA(
    model=settings.NVIDIA_MODEL_PRIMARY,
    api_key=settings.NVIDIA_API_KEY,
).with_fallbacks(
    [ChatNVIDIA(model=settings.NVIDIA_MODEL_FALLBACK, api_key=settings.NVIDIA_API_KEY)]
)

_agent = create_react_agent(_llm, tools=_TOOLS)


async def payment_agent_node(state: DeluxeState) -> dict:
    system_prompt = get_system_prompt(state["role"], state["telegram_id"])
    result = await _agent.ainvoke(
        {"messages": state["messages"]},
        config={"configurable": {"system_message": system_prompt}},
    )
    return {"messages": result["messages"]}
