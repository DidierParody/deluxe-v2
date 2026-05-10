import json
import logging

from langchain_core.tools import tool

from app.db.pool import get_connection

logger = logging.getLogger(__name__)


def _json(obj) -> str:
    """Serialize to JSON string; converts non-serializable types (datetime, Decimal…) via str()."""
    return json.dumps(obj, default=str, ensure_ascii=False)


@tool
async def ver_eventos_disponibles() -> str:
    """Lista todos los eventos en estado publicado o en curso."""
    try:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, description, start_time, end_time
                FROM core.events
                WHERE event_state_id IN (
                    SELECT id FROM catalog.event_states WHERE name IN ('published', 'ongoing')
                )
                ORDER BY start_time ASC
                """
            )
            return _json([dict(r) for r in rows])
    except Exception as exc:
        logger.error(f"ver_eventos_disponibles error: {exc}")
        return _json({"error": str(exc)})


@tool
async def ver_detalle_evento(nombre_evento: str) -> str:
    """Obtiene el detalle completo de un evento buscando por nombre."""
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, description, start_time, end_time
                FROM core.events
                WHERE name ILIKE $1
                LIMIT 1
                """,
                f"%{nombre_evento}%",
            )
            if not row:
                return _json({"status": "error", "message": "Evento no encontrado."})
            return _json({"status": "success", "event": dict(row)})
    except Exception as exc:
        logger.error(f"ver_detalle_evento error: {exc}")
        return _json({"error": str(exc)})
