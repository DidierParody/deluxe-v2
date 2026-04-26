from app.mcp.server import mcp
from app.db.pool import get_connection
import logging

logger = logging.getLogger(__name__)

@mcp.tool()
async def registrar_usuario(telegram_id: int, username: str, email: str, phone_number: str) -> dict:
    """Registra o actualiza un usuario."""
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow("""
                INSERT INTO core.users (username, type_user_id, email, phone_number, telegram_id)
                VALUES (
                    $1,
                    (SELECT id FROM catalog.type_users WHERE name = 'customer'),
                    $2, $3, $4
                )
                ON CONFLICT (telegram_id) DO UPDATE
                    SET username = EXCLUDED.username, updated_at = CURRENT_TIMESTAMP
                RETURNING id, username, email
            """, username, email, phone_number, telegram_id)
            return {"status": "success", "user": dict(row)}
    except Exception as e:
        logger.error(f"Error en registrar_usuario: {e}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def ver_eventos_disponibles() -> list:
    """Lista eventos en estado published u ongoing."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT id, name, description, start_time, end_time 
            FROM core.events 
            WHERE event_state_id IN (
                SELECT id FROM catalog.event_states WHERE name IN ('published', 'ongoing')
            )
            ORDER BY start_time ASC
        """)
        return [dict(r) for r in rows]

@mcp.tool()
async def ver_detalle_evento(nombre_evento: str) -> dict:
    """Obtiene el detalle de un evento buscando por nombre."""
    async with get_connection() as conn:
        row = await conn.fetchrow("""
            SELECT id, name, description, start_time, end_time 
            FROM core.events 
            WHERE name ILIKE $1
            LIMIT 1
        """, f"%{nombre_evento}%")
        if not row:
            return {"status": "error", "message": "Evento no encontrado."}
        return {"status": "success", "event": dict(row)}

@mcp.tool()
async def ver_mesas_disponibles(nombre_evento: str, tipo_mesa: str = None) -> list:
    """
    Consulta disponibilidad de mesas para un evento. 
    Si tipo_mesa se provee, filtra por ese tipo (ej. vip, mesatest2). Si no, devuelve todas las mesas disponibles.
    """
    async with get_connection() as conn:
        # Find event ID first
        evt = await conn.fetchrow("SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1", f"%{nombre_evento}%")
        if not evt:
            return [{"error": "Evento no encontrado"}]
            
        if tipo_mesa:
            rows = await conn.fetch("""
                SELECT dt.number, dt.capacity, tt.name AS tipo, tp.price
                FROM core.dico_tables dt
                JOIN catalog.table_types tt ON tt.id = dt.table_type_id
                JOIN catalog.table_states ts ON ts.id = dt.table_state_id
                LEFT JOIN core.table_prices tp ON tp.table_id = dt.id AND tp.event_id = $1
                WHERE tt.name ILIKE $2 AND ts.name = 'available'
                ORDER BY dt.number
            """, evt['id'], f"%{tipo_mesa}%")
        else:
            rows = await conn.fetch("""
                SELECT dt.number, dt.capacity, tt.name AS tipo, tp.price
                FROM core.dico_tables dt
                JOIN catalog.table_types tt ON tt.id = dt.table_type_id
                JOIN catalog.table_states ts ON ts.id = dt.table_state_id
                LEFT JOIN core.table_prices tp ON tp.table_id = dt.id AND tp.event_id = $1
                WHERE ts.name = 'available'
                ORDER BY tt.name, dt.number
            """, evt['id'])
            
        return [dict(r) for r in rows]

@mcp.tool()
async def ver_tickets_disponibles(nombre_evento: str) -> list:
    """Consulta los tipos de tickets y cantidades disponibles para un evento."""
    async with get_connection() as conn:
        evt = await conn.fetchrow("SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1", f"%{nombre_evento}%")
        if not evt:
            return [{"error": "Evento no encontrado"}]
            
        rows = await conn.fetch("""
            SELECT tt.name, tt.price,
                   COALESCE(tt.max_override, tt.available_quantity) - COUNT(t.id) FILTER (
                       WHERE t.ticket_state_id != (SELECT id FROM catalog.ticket_states WHERE name = 'cancelled')
                   ) AS disponibles
            FROM core.type_tickets tt
            LEFT JOIN transactions.tickets t ON t.type_ticket_id = tt.id
            WHERE tt.event_id = $1
            GROUP BY tt.id, tt.name, tt.price, tt.available_quantity, tt.max_override
            HAVING (COALESCE(tt.max_override, tt.available_quantity) - COUNT(t.id) FILTER (
                WHERE t.ticket_state_id != (SELECT id FROM catalog.ticket_states WHERE name = 'cancelled')
            )) > 0
            ORDER BY tt.price
        """, evt['id'])
        return [dict(r) for r in rows]

@mcp.tool()
async def comprar_tickets(telegram_id: int, nombre_evento: str, tipo_ticket: str, cantidad: int) -> dict:
    """Compra uno o más tickets para un evento. Retorna el order_id que debe pagarse."""
    async with get_connection() as conn:
        async with conn.transaction():
            # Get user id
            user = await conn.fetchrow("SELECT id FROM core.users WHERE telegram_id = $1", telegram_id)
            if not user:
                return {"status": "error", "message": "Debes registrarte primero."}
            user_id = user['id']
            
            # Get event
            evt = await conn.fetchrow("SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1", f"%{nombre_evento}%")
            if not evt:
                return {"status": "error", "message": "Evento no encontrado."}
                
            # Paso 1: bloquear la fila del tipo de ticket con FOR UPDATE (sin GROUP BY)
            tt = await conn.fetchrow("""
                SELECT id, price, COALESCE(max_override, available_quantity) AS cupo
                FROM core.type_tickets
                WHERE event_id = $1 AND name ILIKE $2
                FOR UPDATE
            """, evt['id'], f"%{tipo_ticket}%")
            
            if not tt:
                return {"status": "error", "message": "Tipo de ticket no encontrado."}
            
            # Paso 2: contar los vendidos (no cancelados) por separado
            vendidos_row = await conn.fetchrow("""
                SELECT COUNT(t.id) AS vendidos
                FROM transactions.tickets t
                WHERE t.type_ticket_id = $1
                  AND t.ticket_state_id != (SELECT id FROM catalog.ticket_states WHERE name = 'cancelled')
            """, tt['id'])
            vendidos = vendidos_row['vendidos'] or 0
            
            if tt['cupo'] - vendidos < cantidad:
                return {"status": "error", "message": f"Solo quedan {tt['cupo'] - vendidos} tickets disponibles."}
                
            # Create Order (Caso 7)
            order = await conn.fetchrow("INSERT INTO transactions.orders (user_id, total, status) VALUES ($1, 0, 'pending') RETURNING id", user_id)
            order_id = order['id']
            
            # Insert Tickets and Order Details
            for _ in range(cantidad):
                t = await conn.fetchrow("""
                    INSERT INTO transactions.tickets (user_id, type_ticket_id, ticket_state_id)
                    VALUES ($1, $2, (SELECT id FROM catalog.ticket_states WHERE name = 'pending'))
                    RETURNING id
                """, user_id, tt['id'])
                
                await conn.execute("""
                    INSERT INTO transactions.order_details (order_id, ticket_id, type_ticket_id, quantity, unit_price, discount)
                    VALUES ($1, $2, $3, 1, $4, 0)
                """, order_id, t['id'], tt['id'], tt['price'])
                
            # Update order total
            await conn.execute("""
                UPDATE transactions.orders SET total = (
                    SELECT SUM(unit_price * quantity) FROM transactions.order_details WHERE order_id = $1
                ) WHERE id = $1
            """, order_id)
            
            return {"status": "success", "message": f"Reserva exitosa. Orden ID: {order_id}. Por favor envía comprobante de pago."}

@mcp.tool()
async def reservar_mesa(telegram_id: int, nombre_evento: str, numero_mesa: int) -> dict:
    """Reserva una mesa específica para un evento."""
    async with get_connection() as conn:
        async with conn.transaction():
            user = await conn.fetchrow("SELECT id FROM core.users WHERE telegram_id = $1", telegram_id)
            if not user: return {"status": "error", "message": "Debes registrarte primero."}
            user_id = user['id']
            
            evt = await conn.fetchrow("SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1", f"%{nombre_evento}%")
            if not evt: return {"status": "error", "message": "Evento no encontrado."}
            
            # Validate mesa FOR UPDATE (Caso 6)
            mesa = await conn.fetchrow("""
                SELECT id, table_state_id 
                FROM core.dico_tables 
                WHERE number = $1 AND table_state_id = (SELECT id FROM catalog.table_states WHERE name = 'available')
                FOR UPDATE
            """, numero_mesa)
            
            if not mesa:
                return {"status": "error", "message": "La mesa no está disponible."}
                
            # Get price
            precio = await conn.fetchrow("""
                SELECT price FROM core.table_prices WHERE table_id = $1 AND event_id = $2
            """, mesa['id'], evt['id'])
            
            cost = precio['price'] if precio else 0
            
            # Create Reservation
            res = await conn.fetchrow("""
                INSERT INTO transactions.reservations (reservation_state_id, user_id, table_id, event_id, expires_at)
                VALUES (
                    (SELECT id FROM catalog.reservation_states WHERE name = 'pending'),
                    $1, $2, $3,
                    CASE WHEN CURRENT_TIME < TIME '06:00:00' 
                         THEN DATE_TRUNC('day', CURRENT_TIMESTAMP) + INTERVAL '6 hours'
                         ELSE DATE_TRUNC('day', CURRENT_TIMESTAMP) + INTERVAL '1 day 6 hours'
                    END
                ) RETURNING id
            """, user_id, mesa['id'], evt['id'])
            
            # Mark reserved
            await conn.execute("UPDATE core.dico_tables SET table_state_id = (SELECT id FROM catalog.table_states WHERE name = 'reserved') WHERE id = $1", mesa['id'])
            
            # Create Order
            order = await conn.fetchrow("INSERT INTO transactions.orders (user_id, total, status) VALUES ($1, 0, 'pending') RETURNING id", user_id)
            order_id = order['id']
            
            # Order detail — include table_id for traceability
            await conn.execute("""
                INSERT INTO transactions.order_details (order_id, reservation_id, table_id, quantity, unit_price, discount)
                VALUES ($1, $2, $3, 1, $4, 0)
            """, order_id, res['id'], mesa['id'], cost)
            
            await conn.execute("UPDATE transactions.orders SET total = $2 WHERE id = $1", order_id, cost)
            
            return {"status": "success", "message": f"Mesa {numero_mesa} reservada. Orden ID: {order_id}. Envía tu comprobante de pago.", "order_id": order_id}

@mcp.tool()
async def ver_mis_ordenes(telegram_id: int) -> list:
    """Muestra el historial de órdenes del usuario."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT o.id AS order_id, o.total, o.status, o.ordered_at
            FROM transactions.orders o
            JOIN core.users u ON u.id = o.user_id
            WHERE u.telegram_id = $1
            ORDER BY o.ordered_at DESC LIMIT 5
        """, telegram_id)
        return [dict(r) for r in rows]

@mcp.tool()
async def cancelar_mi_reserva(telegram_id: int, numero_mesa: int) -> dict:
    """Cancela una reserva propia."""
    async with get_connection() as conn:
        async with conn.transaction():
            res = await conn.fetchrow("""
                SELECT r.id, r.table_id
                FROM transactions.reservations r
                JOIN core.users u ON u.id = r.user_id
                JOIN core.dico_tables dt ON dt.id = r.table_id
                WHERE u.telegram_id = $1 AND dt.number = $2
                  AND r.reservation_state_id IN (SELECT id FROM catalog.reservation_states WHERE name IN ('pending', 'confirmed'))
                FOR UPDATE
            """, telegram_id, numero_mesa)
            
            if not res: return {"status": "error", "message": "No se encontró una reserva activa tuya para esta mesa."}
            
            await conn.execute("UPDATE transactions.reservations SET reservation_state_id = (SELECT id FROM catalog.reservation_states WHERE name = 'cancelled') WHERE id = $1", res['id'])
            await conn.execute("UPDATE core.dico_tables SET table_state_id = (SELECT id FROM catalog.table_states WHERE name = 'available') WHERE id = $1", res['table_id'])
            
            return {"status": "success", "message": "Reserva cancelada exitosamente."}

@mcp.tool()
async def ver_metodos_de_pago() -> list:
    """Lista métodos de pago permitidos."""
    async with get_connection() as conn:
        rows = await conn.fetch("SELECT name FROM catalog.payment_methods")
        return [r['name'] for r in rows]
