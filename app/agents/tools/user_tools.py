import json
import logging

from langchain_core.tools import tool

from app.db.pool import get_connection

logger = logging.getLogger(__name__)


def _json(obj) -> str:
    """Serialize to JSON string; converts non-serializable types (datetime, Decimal…) via str()."""
    return json.dumps(obj, default=str, ensure_ascii=False)


@tool
async def registrar_usuario(
    telegram_id: int,
    username: str,
    email: str | None = None,
    phone_number: str | None = None,
) -> str:
    """Registra o actualiza un usuario en el sistema. email y phone_number son opcionales; nunca los inventes."""
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
                    SET username = EXCLUDED.username,
                        email = COALESCE(EXCLUDED.email, core.users.email),
                        phone_number = COALESCE(EXCLUDED.phone_number, core.users.phone_number),
                        updated_at = CURRENT_TIMESTAMP
                RETURNING id, username, email
                """,
                username,
                email,
                phone_number,
                telegram_id,
            )
            return _json({"status": "success", "user": dict(row)})
    except Exception as exc:
        logger.error(f"registrar_usuario error: {exc}")
        return _json({"status": "error", "message": str(exc)})
