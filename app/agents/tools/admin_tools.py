import json
import logging
from datetime import datetime

from langchain_core.tools import tool

from app.db.pool import get_connection

logger = logging.getLogger(__name__)


def _json(obj) -> str:
    """Serialize to JSON string; converts non-serializable types (datetime, Decimal…) via str()."""
    return json.dumps(obj, default=str, ensure_ascii=False)


@tool
async def admin_crear_evento(nombre: str, descripcion: str, start_time: str, end_time: str) -> str:
    """Crea un evento. Fechas en formato YYYY-MM-DD HH:MM:SS."""
    try:
        dt_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        dt_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return _json({"status": "error", "message": "Formato de fecha inválido. Usa YYYY-MM-DD HH:MM:SS."})

    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO core.events (name, description, start_time, end_time, event_state_id)
                VALUES ($1, $2, $3, $4, (SELECT id FROM catalog.event_states WHERE name = 'ongoing'))
                RETURNING id, name
                """,
                nombre,
                descripcion,
                dt_start,
                dt_end,
            )
            return _json({"status": "success", "event": dict(row)})
    except Exception as exc:
        logger.error(f"admin_crear_evento error: {exc}")
        return _json({"error": str(exc)})


@tool
async def admin_cambiar_estado_evento(nombre_evento: str, nuevo_estado: str) -> str:
    """Cambia el estado de un evento (published, ongoing, finished). Para cancelar usa admin_cancelar_evento."""
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE core.events
                SET event_state_id = (SELECT id FROM catalog.event_states WHERE name = $2),
                    updated_at = CURRENT_TIMESTAMP
                WHERE name ILIKE $1
                RETURNING id, name
                """,
                f"%{nombre_evento}%",
                nuevo_estado,
            )
            if not row:
                return _json({"status": "error", "message": "Evento no encontrado."})
            return _json({"status": "success", "event": dict(row)})
    except Exception as exc:
        logger.error(f"admin_cambiar_estado_evento error: {exc}")
        return _json({"error": str(exc)})


@tool
async def admin_cancelar_evento(nombre_evento: str) -> str:
    """Cancela un evento y en cascada cancela tickets y reservas."""
    try:
        async with get_connection() as conn:  # noqa: SIM117
            async with conn.transaction():
                evt = await conn.fetchrow(
                    "SELECT id FROM core.events WHERE name ILIKE $1 FOR UPDATE",
                    f"%{nombre_evento}%",
                )
                if not evt:
                    return _json({"status": "error", "message": "Evento no encontrado."})

                await conn.execute(
                    """
                    UPDATE transactions.tickets
                    SET ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'cancelled')
                    WHERE type_ticket_id IN (SELECT id FROM core.type_tickets WHERE event_id = $1)
                      AND ticket_state_id IN (
                          SELECT id FROM catalog.ticket_states WHERE name IN ('active', 'pending')
                      )
                    """,
                    evt["id"],
                )
                await conn.execute(
                    """
                    UPDATE transactions.reservations
                    SET reservation_state_id = (SELECT id FROM catalog.reservation_states WHERE name = 'cancelled')
                    WHERE event_id = $1
                      AND reservation_state_id IN (
                          SELECT id FROM catalog.reservation_states WHERE name IN ('pending', 'confirmed')
                      )
                    """,
                    evt["id"],
                )
                await conn.execute(
                    "UPDATE core.events SET event_state_id = "
                    "(SELECT id FROM catalog.event_states WHERE name = 'cancelled') WHERE id = $1",
                    evt["id"],
                )
                return _json({
                    "status": "success",
                    "message": "Evento y sus reservas cancelados exitosamente.",
                })
    except Exception as exc:
        logger.error(f"admin_cancelar_evento error: {exc}")
        return _json({"error": str(exc)})


@tool
async def admin_aprobar_orden(order_id: int) -> str:
    """Aprueba manualmente una orden pendiente. Activa tickets y confirma reservas."""
    try:
        async with get_connection() as conn:  # noqa: SIM117
            async with conn.transaction():
                order = await conn.fetchrow(
                    "SELECT id FROM transactions.orders WHERE id = $1 AND status = 'pending' FOR UPDATE",
                    order_id,
                )
                if not order:
                    return _json({"status": "error", "message": "Orden no encontrada o ya procesada."})

                await conn.execute(
                    """
                    UPDATE transactions.tickets
                    SET ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'active')
                    WHERE id IN (
                        SELECT ticket_id FROM transactions.order_details
                        WHERE order_id = $1 AND ticket_id IS NOT NULL
                    )
                    """,
                    order_id,
                )
                await conn.execute(
                    """
                    UPDATE transactions.reservations
                    SET reservation_state_id = (SELECT id FROM catalog.reservation_states WHERE name = 'confirmed')
                    WHERE id IN (
                        SELECT reservation_id FROM transactions.order_details
                        WHERE order_id = $1 AND reservation_id IS NOT NULL
                    )
                    """,
                    order_id,
                )
                await conn.execute(
                    "UPDATE transactions.orders SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                    order_id,
                )
                return _json({"status": "success", "message": f"Orden {order_id} aprobada exitosamente."})
    except Exception as exc:
        logger.error(f"admin_aprobar_orden error: {exc}")
        return _json({"error": str(exc)})


@tool
async def admin_ver_ordenes_pendientes() -> str:
    """Lista las órdenes pendientes de pago."""
    try:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT o.id, o.total, o.ordered_at, u.username
                FROM transactions.orders o
                JOIN core.users u ON u.id = o.user_id
                WHERE o.status = 'pending'
                ORDER BY o.ordered_at ASC
                """
            )
            return _json([dict(r) for r in rows])
    except Exception as exc:
        logger.error(f"admin_ver_ordenes_pendientes error: {exc}")
        return _json({"error": str(exc)})


@tool
async def admin_crear_lote_mesas(
    nombre_tipo: str,
    cantidad: int,
    capacidad: int,
    precio_opcional: float = None,
    nombre_evento_opcional: str = None,
) -> str:
    """
    Crea un grupo de mesas de una sola vez.
    Si precio_opcional y nombre_evento_opcional se envían, asigna precio a todas las mesas para ese evento.
    """
    try:
        async with get_connection() as conn, conn.transaction():
                tt = await conn.fetchrow(
                    "SELECT id FROM catalog.table_types WHERE name ILIKE $1", nombre_tipo
                )
                if not tt:
                    tt = await conn.fetchrow(
                        "INSERT INTO catalog.table_types (name) VALUES ($1) RETURNING id",
                        nombre_tipo.lower(),
                    )
                tt_id = tt["id"]

                max_row = await conn.fetchrow("SELECT MAX(number) AS max_num FROM core.dico_tables")
                start_num = (max_row["max_num"] or 0) + 1

                mesas_creadas = []
                for i in range(cantidad):
                    t = await conn.fetchrow(
                        """
                        INSERT INTO core.dico_tables (number, table_type_id, capacity, table_state_id)
                        VALUES ($1, $2, $3, (SELECT id FROM catalog.table_states WHERE name = 'available'))
                        RETURNING id
                        """,
                        start_num + i,
                        tt_id,
                        capacidad,
                    )
                    mesas_creadas.append(t["id"])

                if precio_opcional is not None and nombre_evento_opcional:
                    evt = await conn.fetchrow(
                        "SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1",
                        f"%{nombre_evento_opcional}%",
                    )
                    if evt:
                        for m_id in mesas_creadas:
                            await conn.execute(
                                """
                                INSERT INTO core.table_prices (table_id, event_id, price)
                                VALUES ($1, $2, $3)
                                ON CONFLICT (table_id, event_id) DO UPDATE SET price = EXCLUDED.price
                                """,
                                m_id,
                                evt["id"],
                                precio_opcional,
                            )

        msg = (
            f"Se crearon {cantidad} mesas tipo '{nombre_tipo}' con capacidad {capacidad} "
            f"(numeradas del {start_num} al {start_num + cantidad - 1})."
        )
        if precio_opcional is not None and nombre_evento_opcional:
            msg += f" Precio ${precio_opcional} asignado para '{nombre_evento_opcional}'."
        return _json({"status": "success", "message": msg})
    except Exception as exc:
        logger.error(f"admin_crear_lote_mesas error: {exc}")
        return _json({"error": str(exc)})


@tool
async def admin_configurar_precio_mesa(nombre_evento: str, numero_mesa: int, precio: float) -> str:
    """Asigna el precio de una mesa específica para un evento."""
    try:
        async with get_connection() as conn:
            evt = await conn.fetchrow(
                "SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1", f"%{nombre_evento}%"
            )
            if not evt:
                return _json({"status": "error", "message": "Evento no encontrado."})

            mesa = await conn.fetchrow("SELECT id FROM core.dico_tables WHERE number = $1", numero_mesa)
            if not mesa:
                return _json({"status": "error", "message": "Mesa no encontrada."})

            await conn.execute(
                """
                INSERT INTO core.table_prices (table_id, event_id, price)
                VALUES ($1, $2, $3)
                ON CONFLICT (table_id, event_id) DO UPDATE SET price = EXCLUDED.price
                """,
                mesa["id"],
                evt["id"],
                precio,
            )
            return _json({
                "status": "success",
                "message": f"Precio ${precio} configurado para mesa {numero_mesa} en '{nombre_evento}'.",
            })
    except Exception as exc:
        logger.error(f"admin_configurar_precio_mesa error: {exc}")
        return _json({"error": str(exc)})


@tool
async def admin_crear_tickets_evento(
    nombre_evento: str, nombre_ticket: str, cantidad: int, precio: float
) -> str:
    """Crea un tipo de entrada (ej. General, VIP) para un evento con cantidad y precio."""
    try:
        async with get_connection() as conn:
            evt = await conn.fetchrow(
                "SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1", f"%{nombre_evento}%"
            )
            if not evt:
                return _json({"status": "error", "message": "Evento no encontrado."})

            await conn.execute(
                "INSERT INTO core.type_tickets (name, event_id, available_quantity, price) VALUES ($1, $2, $3, $4)",
                nombre_ticket,
                evt["id"],
                cantidad,
                precio,
            )
            return _json({
                "status": "success",
                "message": f"{cantidad} tickets '{nombre_ticket}' a ${precio} creados para '{nombre_evento}'.",
            })
    except Exception as exc:
        logger.error(f"admin_crear_tickets_evento error: {exc}")
        return _json({"error": str(exc)})
