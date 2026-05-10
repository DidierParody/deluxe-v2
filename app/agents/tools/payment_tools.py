import logging

from langchain_core.tools import tool

from app.db.pool import get_connection

logger = logging.getLogger(__name__)


@tool
async def ver_mis_ordenes(telegram_id: int) -> list:
    """Muestra el historial de órdenes recientes del usuario."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT o.id AS order_id, o.total, o.status, o.ordered_at
            FROM transactions.orders o
            JOIN core.users u ON u.id = o.user_id
            WHERE u.telegram_id = $1
            ORDER BY o.ordered_at DESC
            LIMIT 5
            """,
            telegram_id,
        )
        return [dict(r) for r in rows]


@tool
async def ver_metodos_de_pago() -> list:
    """Lista los métodos de pago disponibles."""
    async with get_connection() as conn:
        rows = await conn.fetch("SELECT name FROM catalog.payment_methods")
        return [r["name"] for r in rows]
