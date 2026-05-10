import json
import logging

from langchain_core.tools import tool

from app.db.pool import get_connection

logger = logging.getLogger(__name__)


def _json(obj) -> str:
    """Serialize to JSON string; converts non-serializable types (datetime, Decimal…) via str()."""
    return json.dumps(obj, default=str, ensure_ascii=False)


@tool
async def ver_mis_ordenes(telegram_id: int) -> str:
    """Muestra el historial de órdenes recientes del usuario."""
    try:
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
            return _json([dict(r) for r in rows])
    except Exception as exc:
        logger.error(f"ver_mis_ordenes error: {exc}")
        return _json({"error": str(exc)})


@tool
async def ver_metodos_de_pago() -> str:
    """Lista los métodos de pago disponibles."""
    try:
        async with get_connection() as conn:
            rows = await conn.fetch("SELECT name FROM catalog.payment_methods")
            return _json([r["name"] for r in rows])
    except Exception as exc:
        logger.error(f"ver_metodos_de_pago error: {exc}")
        return _json({"error": str(exc)})
