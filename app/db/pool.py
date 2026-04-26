import asyncpg
from typing import Optional
from contextlib import asynccontextmanager
import logging
from app.config import settings

logger = logging.getLogger(__name__)

# Global pool instance
_pool: Optional[asyncpg.Pool] = None

async def init_pool(retries: int = 3, delay: float = 2.0):
    global _pool
    import asyncio
    if _pool is not None:
        return
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Initializing asyncpg connection pool (attempt {attempt}/{retries})...")
            _pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            logger.info("Database pool initialized successfully.")
            return
        except Exception as e:
            _pool = None  # reset so next attempt tries fresh
            logger.error(f"Error initializing database pool (attempt {attempt}): {e}")
            if attempt < retries:
                logger.info(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                raise

async def close_pool():
    global _pool
    if _pool is not None:
        logger.info("Closing database connection pool...")
        await _pool.close()
        _pool = None
        logger.info("Database pool closed.")

@asynccontextmanager
async def get_connection():
    if _pool is None:
        raise RuntimeError("Database pool is not initialized. Call init_pool() first.")
    
    async with _pool.acquire() as conn:
        yield conn
