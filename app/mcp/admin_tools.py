from app.mcp.server import mcp
from app.db.pool import get_connection
import logging

logger = logging.getLogger(__name__)

from datetime import datetime

@mcp.tool()
async def admin_crear_evento(nombre: str, descripcion: str, start_time: str, end_time: str) -> dict:
    """Crea un evento (estado ongoing por defecto). Fechas en formato YYYY-MM-DD HH:MM:SS."""
    try:
        dt_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        dt_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return {"status": "error", "message": "Formato de fecha inválido. Usa YYYY-MM-DD HH:MM:SS."}
        
    async with get_connection() as conn:
        row = await conn.fetchrow("""
            INSERT INTO core.events (name, description, start_time, end_time, event_state_id)
            VALUES ($1, $2, $3, $4, (SELECT id FROM catalog.event_states WHERE name = 'ongoing'))
            RETURNING id, name
        """, nombre, descripcion, dt_start, dt_end)
        return {"status": "success", "event": dict(row)}

@mcp.tool()
async def admin_cambiar_estado_evento(nombre_evento: str, nuevo_estado: str) -> dict:
    """Cambia el estado de un evento (published, ongoing, finished). Para cancelar usar admin_cancelar_evento."""
    async with get_connection() as conn:
        row = await conn.fetchrow("""
            UPDATE core.events 
            SET event_state_id = (SELECT id FROM catalog.event_states WHERE name = $2), updated_at = CURRENT_TIMESTAMP
            WHERE name ILIKE $1
            RETURNING id, name, event_state_id
        """, f"%{nombre_evento}%", nuevo_estado)
        if not row: return {"status": "error", "message": "Evento no encontrado."}
        return {"status": "success"}

@mcp.tool()
async def admin_cancelar_evento(nombre_evento: str) -> dict:
    """Cancela un evento y en cascada cancela tickets y reservas."""
    async with get_connection() as conn:
        async with conn.transaction():
            evt = await conn.fetchrow("SELECT id FROM core.events WHERE name ILIKE $1 FOR UPDATE", f"%{nombre_evento}%")
            if not evt: return {"status": "error", "message": "Evento no encontrado."}
            
            # Cancel tickets
            await conn.execute("""
                UPDATE transactions.tickets SET ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'cancelled')
                WHERE type_ticket_id IN (SELECT id FROM core.type_tickets WHERE event_id = $1)
                  AND ticket_state_id IN (SELECT id FROM catalog.ticket_states WHERE name IN ('active', 'pending'))
            """, evt['id'])
            
            # Cancel reservations
            await conn.execute("""
                UPDATE transactions.reservations SET reservation_state_id = (SELECT id FROM catalog.reservation_states WHERE name = 'cancelled')
                WHERE event_id = $1 AND reservation_state_id IN (SELECT id FROM catalog.reservation_states WHERE name IN ('pending', 'confirmed'))
            """, evt['id'])
            
            # Cancel event (Trigger will release tables)
            await conn.execute("UPDATE core.events SET event_state_id = (SELECT id FROM catalog.event_states WHERE name = 'cancelled') WHERE id = $1", evt['id'])
            return {"status": "success", "message": "Evento y sus reservas canceladas exitosamente."}

@mcp.tool()
async def admin_aprobar_orden(order_id: int) -> dict:
    """Aprueba manualmente una orden pendiente. Activa tickets y confirma reservas."""
    async with get_connection() as conn:
        async with conn.transaction():
            ord_row = await conn.fetchrow("SELECT id, status FROM transactions.orders WHERE id = $1 AND status = 'pending' FOR UPDATE", order_id)
            if not ord_row: return {"status": "error", "message": "Orden no encontrada o no está pendiente."}
            
            # Activate tickets
            await conn.execute("""
                UPDATE transactions.tickets SET ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'active')
                WHERE id IN (SELECT ticket_id FROM transactions.order_details WHERE order_id = $1 AND ticket_id IS NOT NULL)
            """, order_id)
            
            # Confirm reservations
            await conn.execute("""
                UPDATE transactions.reservations SET reservation_state_id = (SELECT id FROM catalog.reservation_states WHERE name = 'confirmed')
                WHERE id IN (SELECT reservation_id FROM transactions.order_details WHERE order_id = $1 AND reservation_id IS NOT NULL)
            """, order_id)
            
            # Approve order
            await conn.execute("UPDATE transactions.orders SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
            
            return {"status": "success", "message": f"Orden {order_id} aprobada exitosamente."}

@mcp.tool()
async def admin_ver_ordenes_pendientes() -> list:
    """Lista las órdenes pendientes de pago."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT o.id, o.total, o.ordered_at, u.username
            FROM transactions.orders o
            JOIN core.users u ON u.id = o.user_id
            WHERE o.status = 'pending'
            ORDER BY o.ordered_at ASC
        """)
        return [dict(r) for r in rows]

@mcp.tool()
async def admin_crear_lote_mesas(nombre_tipo: str, cantidad: int, capacidad: int, precio_opcional: float = None, nombre_evento_opcional: str = None) -> dict:
    """
    Crea un grupo de mesas de una sola vez. 
    - nombre_tipo: El nombre/tipo de las mesas (ej. vip, preventa, mesatest2). Si no existe, se creará.
    - cantidad: Número de mesas a crear.
    - capacidad: Capacidad de personas por mesa.
    - precio_opcional / nombre_evento_opcional: Si se envían, asignará el precio para ese evento a todas las mesas creadas.
    """
    async with get_connection() as conn:
        try:
            async with conn.transaction():
                # 1. Get or create table_type
                tt = await conn.fetchrow("SELECT id FROM catalog.table_types WHERE name ILIKE $1", nombre_tipo)
                if not tt:
                    tt = await conn.fetchrow("INSERT INTO catalog.table_types (name) VALUES ($1) RETURNING id", nombre_tipo.lower())
                tt_id = tt['id']
                
                # 2. Get max table number
                max_row = await conn.fetchrow("SELECT MAX(number) as max_num FROM core.dico_tables")
                start_num = (max_row['max_num'] or 0) + 1
                
                # 3. Insert tables
                mesas_creadas = []
                for i in range(cantidad):
                    num = start_num + i
                    t = await conn.fetchrow("""
                        INSERT INTO core.dico_tables (number, table_type_id, capacity, table_state_id)
                        VALUES ($1, $2, $3, (SELECT id FROM catalog.table_states WHERE name = 'available'))
                        RETURNING id, number
                    """, num, tt_id, capacidad)
                    mesas_creadas.append(t['id'])
                
                # 4. If price and event are provided, assign prices
                if precio_opcional is not None and nombre_evento_opcional:
                    evt = await conn.fetchrow("SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1", f"%{nombre_evento_opcional}%")
                    if evt:
                        for m_id in mesas_creadas:
                            await conn.execute("""
                                INSERT INTO core.table_prices (table_id, event_id, price)
                                VALUES ($1, $2, $3)
                                ON CONFLICT (table_id, event_id) DO UPDATE SET price = EXCLUDED.price
                            """, m_id, evt['id'], precio_opcional)
                            
            mensaje = f"Se crearon {cantidad} mesas llamadas/tipo '{nombre_tipo}' con capacidad para {capacidad} personas (Numeradas del {start_num} al {start_num + cantidad - 1})."
            if precio_opcional is not None and nombre_evento_opcional:
                mensaje += f" Además se les asignó un precio de ${precio_opcional} para el evento '{nombre_evento_opcional}'."
            return {"status": "success", "message": mensaje}
        except Exception as e:
            return {"status": "error", "message": str(e)}

@mcp.tool()
async def admin_configurar_precio_mesa(nombre_evento: str, numero_mesa: int, precio: float) -> dict:
    """Asigna el precio de una mesa específica para un evento."""
    async with get_connection() as conn:
        evt = await conn.fetchrow("SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1", f"%{nombre_evento}%")
        if not evt: return {"status": "error", "message": "Evento no encontrado."}
        
        mesa = await conn.fetchrow("SELECT id FROM core.dico_tables WHERE number = $1", numero_mesa)
        if not mesa: return {"status": "error", "message": "Mesa no encontrada."}
        
        try:
            await conn.execute("""
                INSERT INTO core.table_prices (table_id, event_id, price)
                VALUES ($1, $2, $3)
                ON CONFLICT (table_id, event_id) DO UPDATE SET price = EXCLUDED.price
            """, mesa['id'], evt['id'], precio)
            return {"status": "success", "message": f"Precio ${precio} configurado para mesa {numero_mesa} en evento {nombre_evento}."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

@mcp.tool()
async def admin_crear_tickets_evento(nombre_evento: str, nombre_ticket: str, cantidad: int, precio: float) -> dict:
    """Crea un tipo de entrada (ej. General, VIP) para un evento con cantidad y precio."""
    async with get_connection() as conn:
        evt = await conn.fetchrow("SELECT id FROM core.events WHERE name ILIKE $1 LIMIT 1", f"%{nombre_evento}%")
        if not evt: return {"status": "error", "message": "Evento no encontrado."}
        
        try:
            await conn.execute("""
                INSERT INTO core.type_tickets (name, event_id, available_quantity, price)
                VALUES ($1, $2, $3, $4)
            """, nombre_ticket, evt['id'], cantidad, precio)
            return {"status": "success", "message": f"{cantidad} tickets '{nombre_ticket}' a ${precio} creados para {nombre_evento}."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

# We include a few representative ones to keep files manageable. 
# Full DML tools follow the same pattern.
