import logging
import time
from contextlib import asynccontextmanager

import telegram
from fastapi import FastAPI, Request, Response

import app.bot_registry as bot_registry
from app.agents.graph import compile_graph
from app.bots.deluxeam import create_bot_am
from app.bots.deluxecs import create_bot_cs
from app.cache.redis_client import close_redis, init_redis
from app.config import settings
from app.db.pool import close_pool, init_pool

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "msg": %(message)s}',
)
logger = logging.getLogger(__name__)

bot_cs_app = create_bot_cs()
bot_am_app = create_bot_am()

bot_registry.bot_cs_app = bot_cs_app
bot_registry.bot_am_app = bot_am_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    redis = await init_redis()

    # Compile and register the LangGraph agent graph
    bot_registry.graph = compile_graph(redis)

    if settings.ENABLE_BACKGROUND_SCHEDULER:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        from app.scheduler.jobs import finalizar_eventos_expirados, liberar_mesas_expiradas

        scheduler = AsyncIOScheduler()
        scheduler.add_job(finalizar_eventos_expirados, "interval", minutes=5)
        scheduler.add_job(liberar_mesas_expiradas, "interval", minutes=10)
        scheduler.start()
        app.state.scheduler = scheduler

    await bot_cs_app.initialize()
    await bot_cs_app.bot.set_webhook(
        url=f"{settings.WEBHOOK_BASE_URL}/webhook/deluxecs",
        allowed_updates=["message", "callback_query"],
        secret_token=settings.WEBHOOK_SECRET_TOKEN or None,
    )

    await bot_am_app.initialize()
    await bot_am_app.bot.set_webhook(
        url=f"{settings.WEBHOOK_BASE_URL}/webhook/deluxeam",
        allowed_updates=["message", "callback_query", "message_reaction"],
        secret_token=settings.WEBHOOK_SECRET_TOKEN or None,
    )

    yield

    if settings.ENABLE_BACKGROUND_SCHEDULER and hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()

    for bot_app, name in [(bot_cs_app, "CS"), (bot_am_app, "AM")]:
        try:
            await bot_app.bot.delete_webhook()
        except Exception as exc:
            logger.warning(f"{name} delete_webhook failed (ignored): {exc}")
        try:
            await bot_app.shutdown()
        except Exception as exc:
            logger.warning(f"{name} shutdown failed: {exc}")

    await close_redis()
    await close_pool()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def telegram_signature_middleware(request: Request, call_next):
    """Validates X-Telegram-Bot-Api-Secret-Token on webhook paths."""
    if request.url.path.startswith("/webhook/") and settings.WEBHOOK_SECRET_TOKEN:
        received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if received != settings.WEBHOOK_SECRET_TOKEN:
            return Response(status_code=403, content="Forbidden")
    return await call_next(request)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "redis_configured": bool(settings.REDIS_URL or settings.UPSTASH_REDIS_REST_URL),
        "memory_enabled": settings.REDIS_MEMORY_ENABLED,
    }


@app.post("/webhook/deluxecs")
async def webhook_cs(request: Request):
    t0 = time.monotonic()
    update = telegram.Update.de_json(await request.json(), bot_cs_app.bot)
    await bot_cs_app.process_update(update)
    logger.info('"webhook": "deluxecs", "duration_ms": %.0f', (time.monotonic() - t0) * 1000)
    return Response(status_code=200)


@app.post("/webhook/deluxeam")
async def webhook_am(request: Request):
    t0 = time.monotonic()
    update = telegram.Update.de_json(await request.json(), bot_am_app.bot)
    await bot_am_app.process_update(update)
    logger.info('"webhook": "deluxeam", "duration_ms": %.0f', (time.monotonic() - t0) * 1000)
    return Response(status_code=200)
