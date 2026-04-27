import asyncio
from app.db.pool import init_pool, close_pool, get_connection

async def sync_sequences():
    await init_pool()
    async with get_connection() as conn:
        tables = [
            'catalog.type_users', 'catalog.event_states', 'catalog.reservation_states',
            'catalog.table_states', 'catalog.table_types', 'catalog.ticket_states', 'catalog.payment_methods',
            'core.type_tickets', 'core.table_prices', 'core.users', 'core.events', 'core.dico_tables',
            'transactions.orders', 'transactions.order_details', 'transactions.tickets', 'transactions.reservations',
            'transactions.payments', 'system.pairing_codes', 'system.admin_actions_log'
        ]
        for t in tables:
            try:
                query = f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE((SELECT MAX(id) FROM {t}), 1))"
                await conn.execute(query)
                print(f'Synced {t}')
            except Exception as e:
                print(f'Skipped {t}: {e}')
    await close_pool()

asyncio.run(sync_sequences())
