import string
import secrets
from datetime import datetime, timedelta
from app.db.pool import get_connection

async def generate_pairing_code(telegram_id: int) -> str:
    alphabet = string.ascii_uppercase + string.digits
    code = ''.join(secrets.choice(alphabet) for _ in range(6))
    
    async with get_connection() as conn:
        await conn.execute("""
            INSERT INTO system.pairing_codes (code, telegram_id, expires_at)
            VALUES ($1, $2, CURRENT_TIMESTAMP + interval '5 minutes')
        """, code, telegram_id)
        
    return code

async def verify_pairing_code(code: str, telegram_id: int) -> bool:
    async with get_connection() as conn:
        row = await conn.fetchrow("""
            SELECT id FROM system.pairing_codes
            WHERE code = $1 AND telegram_id = $2 AND expires_at > CURRENT_TIMESTAMP
        """, code, telegram_id)
        return row is not None
