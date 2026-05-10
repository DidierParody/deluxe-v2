import json
import logging

from langchain_core.tools import tool

from app.db.pool import get_connection

logger = logging.getLogger(__name__)


def _json(obj) -> str:
    """Serialize to JSON string; converts non-serializable types (datetime, Decimal…) via str()."""
    return json.dumps(obj, default=str, ensure_ascii=False)


@tool
async def ver_tickets_disponibles(nombre_evento: str) -> str:
    """Consulta los tipos de tickets y cantidades disponibles para un evento."""
    try:
        async with get_connection() as conn:
            evt = await conn.fetchrow(
                "SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1",
                f"%{nombre_evento}%",
            )
            if not evt:
                return _json([{"error": "Evento no encontrado"}])

            rows = await conn.fetch(
                """
                SELECT tt.name, tt.price,
                       COALESCE(tt.max_override, tt.available_quantity)
                       - COUNT(t.id) FILTER (
                           WHERE t.ticket_state_id != (
                               SELECT id FROM catalog.ticket_states WHERE name = 'cancelled'
                           )
                       ) AS disponibles
                FROM core.type_tickets tt
                LEFT JOIN transactions.tickets t ON t.type_ticket_id = tt.id
                WHERE tt.event_id = $1
                GROUP BY tt.id, tt.name, tt.price, tt.available_quantity, tt.max_override
                HAVING (
                    COALESCE(tt.max_override, tt.available_quantity)
                    - COUNT(t.id) FILTER (
                        WHERE t.ticket_state_id != (
                            SELECT id FROM catalog.ticket_states WHERE name = 'cancelled'
                        )
                    )
                ) > 0
                ORDER BY tt.price
                """,
                evt["id"],
            )
            return _json([dict(r) for r in rows])
    except Exception as exc:
        logger.error(f"ver_tickets_disponibles error: {exc}")
        return _json({"error": str(exc)})


@tool
async def comprar_tickets(
    telegram_id: int, nombre_evento: str, tipo_ticket: str, cantidad: int
) -> str:
    """
    Compra uno o más tickets para un evento.
    Retorna el order_id que el usuario debe pagar enviando su comprobante.
    """
    try:
        async with get_connection() as conn:  # noqa: SIM117
            async with conn.transaction():
                user = await conn.fetchrow(
                    "SELECT id FROM core.users WHERE telegram_id = $1", telegram_id
                )
                if not user:
                    return _json({"status": "error", "message": "Debes registrarte primero."})

                evt = await conn.fetchrow(
                    "SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1",
                    f"%{nombre_evento}%",
                )
                if not evt:
                    return _json({"status": "error", "message": "Evento no encontrado."})

                # Lock the ticket type row AND count sold tickets in the same query
                # to eliminate the race condition between FOR UPDATE and COUNT.
                tt = await conn.fetchrow(
                    """
                    SELECT id, price,
                           COALESCE(max_override, available_quantity)
                           - (
                               SELECT COUNT(*) FROM transactions.tickets t2
                               WHERE t2.type_ticket_id = tt.id
                                 AND t2.ticket_state_id != (
                                     SELECT id FROM catalog.ticket_states WHERE name = 'cancelled'
                                 )
                           ) AS disponibles
                    FROM core.type_tickets tt
                    WHERE event_id = $1 AND name ILIKE $2
                    FOR UPDATE
                    """,
                    evt["id"],
                    f"%{tipo_ticket}%",
                )
                if not tt:
                    return _json({"status": "error", "message": "Tipo de ticket no encontrado."})

                disponibles = tt["disponibles"] or 0
                if disponibles < cantidad:
                    return _json(
                        {
                            "status": "error",
                            "message": f"Solo quedan {disponibles} tickets disponibles.",
                        }
                    )

                order = await conn.fetchrow(
                    "INSERT INTO transactions.orders (user_id, total, status) VALUES ($1, 0, 'pending') RETURNING id",
                    user["id"],
                )
                order_id = order["id"]

                for _ in range(cantidad):
                    t = await conn.fetchrow(
                        """
                        INSERT INTO transactions.tickets (user_id, type_ticket_id, ticket_state_id)
                        VALUES ($1, $2, (SELECT id FROM catalog.ticket_states WHERE name = 'pending'))
                        RETURNING id
                        """,
                        user["id"],
                        tt["id"],
                    )
                    await conn.execute(
                        """
                        INSERT INTO transactions.order_details
                            (order_id, ticket_id, type_ticket_id, quantity, unit_price, discount)
                        VALUES ($1, $2, $3, 1, $4, 0)
                        """,
                        order_id,
                        t["id"],
                        tt["id"],
                        tt["price"],
                    )

                await conn.execute(
                    """
                    UPDATE transactions.orders
                    SET total = (
                        SELECT SUM(unit_price * quantity)
                        FROM transactions.order_details
                        WHERE order_id = $1
                    )
                    WHERE id = $1
                    """,
                    order_id,
                )
                return _json(
                    {
                        "status": "success",
                        "message": f"Reserva exitosa. Orden ID: {order_id}. Por favor envía comprobante de pago.",
                        "order_id": order_id,
                    }
                )
    except Exception as exc:
        logger.error(f"comprar_tickets error: {exc}")
        return _json({"error": str(exc)})
