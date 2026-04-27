import json
import logging
import os
from typing import Dict, List, Any
from app.llm.resilience import call_with_resilience
from app.llm.prompts import get_system_prompt
from app.idempotency.store import idempotency_store
from app.mcp.server import mcp

# Setup specialized LLM debug logger
os.makedirs("logs", exist_ok=True)
file_handler = logging.FileHandler("logs/llm_debug.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logger = logging.getLogger("LLM_ORCHESTRATOR")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

# Simple in-memory memory for conversation history per telegram chat_id
# For production, this should be in Redis or DB.
_conversations: Dict[int, List[Dict[str, Any]]] = {}

async def process_message(chat_id: int, telegram_id: int, role: str, text: str, update_id: int) -> str:
    """
    Main orchestrator loop.
    1. Checks idempotency.
    2. Calls LLM with history and tools.
    3. If tool calls requested, executes them and loops.
    4. Returns final text.
    """
    logger.info(f"--- NUEVO MENSAJE de {telegram_id} (Role: {role}) ---")
    logger.info(f"Texto del usuario: {text}")
    
    # 1. Idempotency Check
    cached = await idempotency_store.get(update_id)
    if cached is not None:
        logger.info(f"Idempotency hit para el update {update_id}. Devolviendo cache.")
        return cached

    # 2. Conversation history
    if chat_id not in _conversations:
        _conversations[chat_id] = [
            {"role": "system", "content": get_system_prompt(role, telegram_id)}
        ]
    
    _conversations[chat_id].append({"role": "user", "content": text})
    
    # 3. Get tools
    tools = await mcp.get_role_tools(role)
    
    max_loops = 5
    loops = 0
    
    while loops < max_loops:
        loops += 1
        
        # Call LLM
        logger.info(f"[Bucle {loops}] Enviando historial al LLM (Mensajes: {len(_conversations[chat_id])})")
        response = await call_with_resilience(_conversations[chat_id], tools)
        
        if response.text:
            logger.info(f"Respuesta final en texto del LLM: {response.text}")
            _conversations[chat_id].append({"role": "assistant", "content": response.text})
            # Cache the successful text response
            await idempotency_store.set(update_id, response.text)
            return response.text
            
        elif response.tool_calls:
            logger.info(f"El LLM decidió ejecutar {len(response.tool_calls)} herramienta(s).")
            # Append the tool_calls to history so providers can format them correctly
            _conversations[chat_id].append({
                "role": "assistant", 
                "content": None,
                "tool_calls": response.tool_calls
            })
            
            for tc in response.tool_calls:
                logger.info(f"Ejecutando herramienta: {tc.name} con argumentos: {tc.arguments}")
                try:
                    # Execute tool via FastMCP
                    tool_names = [t.name for t in await mcp.list_tools()]
                    if tc.name in tool_names:
                        tool_obj = await mcp.get_tool(tc.name)
                        tool_func = tool_obj.fn
                        
                        # Add telegram_id to kwargs if the function expects it
                        kwargs = tc.arguments or {}
                        import inspect
                        sig = inspect.signature(tool_func)
                        if "telegram_id" in sig.parameters:
                            kwargs["telegram_id"] = telegram_id
                            
                        # Call it (assuming async tools)
                        import asyncio
                        if asyncio.iscoroutinefunction(tool_func):
                            result = await tool_func(**kwargs)
                        else:
                            result = tool_func(**kwargs)
                            
                        logger.info(f"Resultado de {tc.name}: {result}")
                        
                        # Append result to history
                        _conversations[chat_id].append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.name,
                            "content": json.dumps(result, default=str)
                        })
                    else:
                        logger.warning(f"La herramienta {tc.name} no fue encontrada en el catálogo.")
                        _conversations[chat_id].append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.name,
                            "content": json.dumps({"error": "Tool not found"})
                        })
                except Exception as e:
                    logger.error(f"Error interno al ejecutar herramienta {tc.name}: {e}")
                    _conversations[chat_id].append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": json.dumps({"error": str(e)})
                    })
        else:
            logger.error("El LLM no devolvió texto ni llamadas a herramientas.")
            return "No recibí una respuesta válida del sistema."
            
    logger.warning("Operación abortada por exceder el máximo de bucles (max_loops).")
    return "Lo siento, la operación ha tardado demasiado y fue abortada."
