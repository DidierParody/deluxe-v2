import json
import logging
import os
from typing import Any, Dict, List

from app.idempotency.store import idempotency_store
from app.llm.conversation_store import conversation_store
from app.llm.prompts import compose_system_prompt, get_system_prompt
from app.llm.resilience import call_with_resilience
from app.llm.session_memory import build_memory_prompt, derive_session_patch
from app.mcp.server import mcp

os.makedirs("logs", exist_ok=True)
file_handler = logging.FileHandler("logs/llm_debug.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logger = logging.getLogger("LLM_ORCHESTRATOR")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)


async def process_message(chat_id: int, telegram_id: int, role: str, text: str, update_id: int) -> str:
    """
    Main orchestrator loop.
    1. Checks idempotency.
    2. Rebuilds short-term conversation memory.
    3. Calls LLM with history and tools.
    4. If tool calls requested, executes them and loops.
    5. Returns final text.
    """
    logger.info(f"--- NUEVO MENSAJE de {telegram_id} (Role: {role}) ---")
    logger.info(f"Texto del usuario: {text}")

    cached = await idempotency_store.get(update_id)
    if cached is not None:
        logger.info(f"Idempotency hit para el update {update_id}. Devolviendo cache.")
        return cached

    await conversation_store.merge_session(role, chat_id, derive_session_patch(role, text))
    session = await conversation_store.load_session(role, chat_id)
    persisted_history = await conversation_store.load_conversation(role, chat_id)
    conversation = _build_runtime_conversation(role, telegram_id, persisted_history, session)

    user_message = {"role": "user", "content": text}
    conversation.append(user_message)
    await conversation_store.append_messages(role, chat_id, [user_message])

    tools = await mcp.get_role_tools(role)

    max_loops = 5
    loops = 0

    while loops < max_loops:
        loops += 1
        logger.info(f"[Bucle {loops}] Enviando historial al LLM (Mensajes: {len(conversation)})")
        response = await call_with_resilience(conversation, tools)

        if response.text:
            logger.info(f"Respuesta final en texto del LLM: {response.text}")
            assistant_message = {"role": "assistant", "content": response.text}
            conversation.append(assistant_message)
            await conversation_store.append_messages(role, chat_id, [assistant_message])
            await idempotency_store.set(update_id, response.text)
            return response.text

        if response.tool_calls:
            logger.info(f"El LLM decidio ejecutar {len(response.tool_calls)} herramienta(s).")
            assistant_tool_message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [_tool_call_to_dict(tool_call) for tool_call in response.tool_calls],
            }
            conversation.append(assistant_tool_message)
            await conversation_store.append_messages(role, chat_id, [assistant_tool_message])

            for tc in response.tool_calls:
                logger.info(f"Ejecutando herramienta: {tc.name} con argumentos: {tc.arguments}")
                tool_message = await _execute_tool_call(tc, telegram_id)
                conversation.append(tool_message)
                await conversation_store.append_messages(role, chat_id, [tool_message])
            continue

        logger.error("El LLM no devolvio texto ni llamadas a herramientas.")
        return "No recibi una respuesta valida del sistema."

    logger.warning("Operacion abortada por exceder el maximo de bucles (max_loops).")
    return "Lo siento, la operacion ha tardado demasiado y fue abortada."


def _build_runtime_conversation(
    role: str,
    telegram_id: int,
    persisted_history: List[Dict[str, Any]],
    session: Dict[str, Any],
) -> List[Dict[str, Any]]:
    memory_prompt = build_memory_prompt(session, has_recent_history=bool(persisted_history))
    system_message = {
        "role": "system",
        "content": compose_system_prompt(
            get_system_prompt(role, telegram_id),
            memory_prompt,
        ),
    }
    history = [message for message in persisted_history if message.get("role") != "system"]
    return [system_message, *history]


async def _execute_tool_call(tool_call, telegram_id: int) -> Dict[str, Any]:
    try:
        tool_names = [tool.name for tool in await mcp.list_tools()]
        if tool_call.name not in tool_names:
            logger.warning(f"La herramienta {tool_call.name} no fue encontrada en el catalogo.")
            return {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.name,
                "content": json.dumps({"error": "Tool not found"}),
            }

        tool_obj = await mcp.get_tool(tool_call.name)
        tool_func = tool_obj.fn

        kwargs = tool_call.arguments or {}
        import inspect
        sig = inspect.signature(tool_func)
        if "telegram_id" in sig.parameters:
            kwargs["telegram_id"] = telegram_id

        import asyncio
        if asyncio.iscoroutinefunction(tool_func):
            result = await tool_func(**kwargs)
        else:
            result = tool_func(**kwargs)

        logger.info(f"Resultado de {tool_call.name}: {result}")
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.name,
            "content": json.dumps(result, default=str),
        }
    except Exception as exc:
        logger.error(f"Error interno al ejecutar herramienta {tool_call.name}: {exc}")
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.name,
            "content": json.dumps({"error": str(exc)}),
        }


def _tool_call_to_dict(tool_call) -> Dict[str, Any]:
    return {
        "id": tool_call.id,
        "name": tool_call.name,
        "arguments": tool_call.arguments,
    }
