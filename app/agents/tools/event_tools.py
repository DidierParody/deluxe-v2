import logging

from langchain_core.tools import tool

from app.db.pool import get_connection

logger = logging.getLogger(__name__)


@tool
async def ver_eventos_disponibles() -> list:
    """Lista todos los eventos en estado publicado o en curso."""
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
        return [dict(r) for r in rows]


@tool
async def ver_detalle_evento(nombre_evento: str) -> dict:
    """Obtiene el detalle completo de un evento buscando por nombre."""
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
            return {"status": "error", "message": "Evento no encontrado."}
        return {"status": "success", "event": dict(row)}
