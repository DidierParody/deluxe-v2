import logging
from langchain_core.tools import tool
from app.db.pool import get_connection

logger = logging.getLogger(__name__)


@tool
async def registrar_usuario(telegram_id: int, username: str, email: str, phone_number: str) -> dict:
    """Registra o actualiza un usuario en el sistema."""
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO core.users (username, type_user_id, email, phone_number, telegram_id)
                VALUES (
                    $1,
                    (SELECT id FROM catalog.type_users WHERE name = 'customer'),
                    $2, $3, $4
                )
                ON CONFLICT (telegram_id) DO UPDATE
                    SET username = EXCLUDED.username, updated_at = CURRENT_TIMESTAMP
                RETURNING id, username, email
                """,
                username, email, phone_number, telegram_id,
            )
            return {"status": "success", "user": dict(row)}
    except Exception as exc:
        logger.error(f"registrar_usuario error: {exc}")
        return {"status": "error", "message": str(exc)}
