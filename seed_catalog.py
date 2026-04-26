import asyncio
from app.db.pool import init_pool, close_pool, get_connection

async def main():
    await init_pool()
    async with get_connection() as conn:
        async with conn.transaction():
            # Seed type_users
            await conn.execute("INSERT INTO catalog.type_users (id, name) VALUES (1, 'admin'), (2, 'customer') ON CONFLICT (id) DO NOTHING")
            # Seed event_states
            await conn.execute("INSERT INTO catalog.event_states (id, name) VALUES (1, 'ongoing'), (2, 'finished'), (3, 'cancelled') ON CONFLICT (id) DO NOTHING")
            # Seed reservation_states
            await conn.execute("INSERT INTO catalog.reservation_states (id, name) VALUES (1, 'confirmed'), (2, 'completed'), (3, 'cancelled') ON CONFLICT (id) DO NOTHING")
            # Seed table_states
            await conn.execute("INSERT INTO catalog.table_states (id, name) VALUES (1, 'available'), (2, 'reserved'), (3, 'occupied') ON CONFLICT (id) DO NOTHING")
            # Seed table_types
            await conn.execute("INSERT INTO catalog.table_types (id, name) VALUES (1, 'vip'), (2, 'regular') ON CONFLICT (id) DO NOTHING")
            # Seed ticket_states
            await conn.execute("INSERT INTO catalog.ticket_states (id, name) VALUES (1, 'active'), (2, 'used'), (3, 'cancelled') ON CONFLICT (id) DO NOTHING")
            # Seed payment_methods
            await conn.execute("INSERT INTO catalog.payment_methods (id, name) VALUES (1, 'transfer'), (2, 'credit_card') ON CONFLICT (id) DO NOTHING")
            
        print("Catalog tables seeded successfully!")
    await close_pool()

asyncio.run(main())
