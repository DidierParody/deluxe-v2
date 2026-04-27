import asyncio
from app.db.pool import init_pool, close_pool, get_connection

async def seed_missing_states():
    await init_pool()
    async with get_connection() as conn:
        # Ticket states faltantes
        missing_ticket_states = ['pending']
        for name in missing_ticket_states:
            exists = await conn.fetchval(
                "SELECT id FROM catalog.ticket_states WHERE name = $1", name
            )
            if not exists:
                await conn.execute(
                    "INSERT INTO catalog.ticket_states (name) VALUES ($1)", name
                )
                print(f"  Insertado ticket_state: '{name}'")
            else:
                print(f"  Ya existe ticket_state: '{name}' (id={exists})")

        print("\n=== catalog.ticket_states final ===")
        rows = await conn.fetch("SELECT * FROM catalog.ticket_states ORDER BY id")
        for r in rows:
            print(dict(r))

    await close_pool()

asyncio.run(seed_missing_states())
