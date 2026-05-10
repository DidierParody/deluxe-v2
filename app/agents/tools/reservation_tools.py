import logging
from langchain_core.tools import tool
from app.db.pool import get_connection

logger = logging.getLogger(__name__)


@tool
async def ver_mesas_disponibles(nombre_evento: str, tipo_mesa: str = None) -> list:
    """
    Consulta disponibilidad de mesas para un evento.
    Filtra por tipo si se indica (ej. vip, regular). Sin tipo devuelve todas.
    """
    async with get_connection() as conn:
        evt = await conn.fetchrow(
            "SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1",
            f"%{nombre_evento}%",
        )
        if not evt:
            return [{"error": "Evento no encontrado"}]

        if tipo_mesa:
            rows = await conn.fetch(
                """
                SELECT dt.number, dt.capacity, tt.name AS tipo, tp.price
                FROM core.dico_tables dt
                JOIN catalog.table_types tt ON tt.id = dt.table_type_id
                JOIN catalog.table_states ts ON ts.id = dt.table_state_id
                LEFT JOIN core.table_prices tp ON tp.table_id = dt.id AND tp.event_id = $1
                WHERE tt.name ILIKE $2 AND ts.name = 'available'
                ORDER BY dt.number
                """,
                evt["id"], f"%{tipo_mesa}%",
            )
        else:
            rows = await conn.fetch(
                """
                SELECT dt.number, dt.capacity, tt.name AS tipo, tp.price
                FROM core.dico_tables dt
                JOIN catalog.table_types tt ON tt.id = dt.table_type_id
                JOIN catalog.table_states ts ON ts.id = dt.table_state_id
                LEFT JOIN core.table_prices tp ON tp.table_id = dt.id AND tp.event_id = $1
                WHERE ts.name = 'available'
                ORDER BY tt.name, dt.number
                """,
                evt["id"],
            )
        return [dict(r) for r in rows]


@tool
async def reservar_mesa(telegram_id: int, nombre_evento: str, numero_mesa: int) -> dict:
    """Reserva una mesa específica para un evento y crea la orden de pago correspondiente."""
    async with get_connection() as conn:
        async with conn.transaction():
            user = await conn.fetchrow(
                "SELECT id FROM core.users WHERE telegram_id = $1", telegram_id
            )
            if not user:
                return {"status": "error", "message": "Debes registrarte primero."}

            evt = await conn.fetchrow(
                "SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1",
                f"%{nombre_evento}%",
            )
            if not evt:
                return {"status": "error", "message": "Evento no encontrado."}

            mesa = await conn.fetchrow(
                """
                SELECT id FROM core.dico_tables
                WHERE number = $1
                  AND table_state_id = (SELECT id FROM catalog.table_states WHERE name = 'available')
                FOR UPDATE
                """,
                numero_mesa,
            )
            if not mesa:
                return {"status": "error", "message": "La mesa no está disponible."}

            precio = await conn.fetchrow(
                "SELECT price FROM core.table_prices WHERE table_id = $1 AND event_id = $2",
                mesa["id"], evt["id"],
            )
            cost = precio["price"] if precio else 0

            res = await conn.fetchrow(
                """
                INSERT INTO transactions.reservations
                    (reservation_state_id, user_id, table_id, event_id, expires_at)
                VALUES (
                    (SELECT id FROM catalog.reservation_states WHERE name = 'pending'),
                    $1, $2, $3,
                    CASE WHEN CURRENT_TIME < TIME '06:00:00'
                         THEN DATE_TRUNC('day', CURRENT_TIMESTAMP) + INTERVAL '6 hours'
                         ELSE DATE_TRUNC('day', CURRENT_TIMESTAMP) + INTERVAL '1 day 6 hours'
                    END
                ) RETURNING id
                """,
                user["id"], mesa["id"], evt["id"],
            )
            await conn.execute(
                "UPDATE core.dico_tables SET table_state_id = "
                "(SELECT id FROM catalog.table_states WHERE name = 'reserved') WHERE id = $1",
                mesa["id"],
            )
            order = await conn.fetchrow(
                "INSERT INTO transactions.orders (user_id, total, status) VALUES ($1, 0, 'pending') RETURNING id",
                user["id"],
            )
            await conn.execute(
                """
                INSERT INTO transactions.order_details
                    (order_id, reservation_id, table_id, quantity, unit_price, discount)
                VALUES ($1, $2, $3, 1, $4, 0)
                """,
                order["id"], res["id"], mesa["id"], cost,
            )
            await conn.execute(
                "UPDATE transactions.orders SET total = $2 WHERE id = $1",
                order["id"], cost,
            )
            return {
                "status": "success",
                "message": f"Mesa {numero_mesa} reservada. Orden ID: {order['id']}. Envía tu comprobante de pago.",
                "order_id": order["id"],
            }


@tool
async def cancelar_mi_reserva(telegram_id: int, numero_mesa: int) -> dict:
    """Cancela una reserva activa del usuario para la mesa indicada."""
    async with get_connection() as conn:
        async with conn.transaction():
            res = await conn.fetchrow(
                """
                SELECT r.id, r.table_id
                FROM transactions.reservations r
                JOIN core.users u ON u.id = r.user_id
                JOIN core.dico_tables dt ON dt.id = r.table_id
                WHERE u.telegram_id = $1 AND dt.number = $2
                  AND r.reservation_state_id IN (
                      SELECT id FROM catalog.reservation_states WHERE name IN ('pending', 'confirmed')
                  )
                FOR UPDATE
                """,
                telegram_id, numero_mesa,
            )
            if not res:
                return {"status": "error", "message": "No se encontró una reserva activa para esta mesa."}

            await conn.execute(
                "UPDATE transactions.reservations SET reservation_state_id = "
                "(SELECT id FROM catalog.reservation_states WHERE name = 'cancelled') WHERE id = $1",
                res["id"],
            )
            await conn.execute(
                "UPDATE core.dico_tables SET table_state_id = "
                "(SELECT id FROM catalog.table_states WHERE name = 'available') WHERE id = $1",
                res["table_id"],
            )
            return {"status": "success", "message": "Reserva cancelada exitosamente."}
