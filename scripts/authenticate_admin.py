import asyncio
import argparse
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.pool import init_pool, close_pool, get_connection
from app.auth.pairing import verify_pairing_code

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", required=True)
    parser.add_argument("--telegram-id", required=True, type=int)
    args = parser.parse_args()

    await init_pool()
    try:
        if await verify_pairing_code(args.code, args.telegram_id):
            async with get_connection() as conn:
                async with conn.transaction():
                    # Upsert the user as admin, or update if exists
                    await conn.execute("""
                        INSERT INTO core.users (username, type_user_id, email, phone_number, telegram_id)
                        VALUES (
                            $2::varchar, 
                            (SELECT id FROM catalog.type_users WHERE name = 'admin'), 
                            $3::varchar, 
                            $4::varchar, 
                            $1::bigint
                        )
                        ON CONFLICT (telegram_id) DO UPDATE
                            SET type_user_id = (SELECT id FROM catalog.type_users WHERE name = 'admin')
                    """, args.telegram_id, str(args.telegram_id), f"{args.telegram_id}@admin.com", str(args.telegram_id))
                    
                    # Delete code
                    await conn.execute("DELETE FROM system.pairing_codes WHERE code = $1", args.code)
                    
                    # Log
                    await conn.execute("""
                        INSERT INTO system.admin_actions_log (admin_id, action, payload)
                        VALUES ($1, 'PROMOTED_TO_ADMIN', '{"code_used": true}')
                    """, args.telegram_id)
                    
            print(f"Usuario {args.telegram_id} autenticado y promovido a ADMIN exitosamente.")
        else:
            print("Código inválido o expirado.")
    finally:
        await close_pool()

if __name__ == "__main__":
    asyncio.run(main())
