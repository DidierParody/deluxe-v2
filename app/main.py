import logging
from contextlib import asynccontextmanager

import telegram
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, Response

import app.bot_registry as bot_registry
from app.bots.deluxeam import create_bot_am
from app.bots.deluxecs import create_bot_cs
from app.config import settings
from app.db.pool import close_pool, init_pool
from app.scheduler.jobs import (
    finalizar_eventos_expirados,
    liberar_mesas_expiradas,
    mantener_webhook_activo,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instancia de bots (global scope)
bot_cs_app = create_bot_cs()
bot_am_app = create_bot_am()
scheduler = AsyncIOScheduler()

# Registrar en el registry compartido para evitar imports circulares
bot_registry.bot_cs_app = bot_cs_app
bot_registry.bot_am_app = bot_am_app


def _is_scheduler_enabled() -> bool:
    return settings.ENABLE_BACKGROUND_SCHEDULER


def _is_self_ping_enabled() -> bool:
    return settings.ENABLE_SELF_PING


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar DB
    await init_pool()

    # Inicializar Scheduler
    scheduler_started = False
    if _is_scheduler_enabled() or _is_self_ping_enabled():
        if _is_scheduler_enabled():
            scheduler.add_job(finalizar_eventos_expirados, "interval", minutes=5)
            scheduler.add_job(liberar_mesas_expiradas, "interval", minutes=10)
        if _is_self_ping_enabled():
            scheduler.add_job(mantener_webhook_activo, "interval", minutes=10)
        scheduler.start()
        scheduler_started = True

    # Inicializar bots y webhooks
    await bot_cs_app.initialize()
    await bot_cs_app.bot.set_webhook(
        url=f"{settings.WEBHOOK_BASE_URL}/webhook/deluxecs",
        allowed_updates=["message", "callback_query"],
    )

    await bot_am_app.initialize()
    await bot_am_app.bot.set_webhook(
        url=f"{settings.WEBHOOK_BASE_URL}/webhook/deluxeam",
        allowed_updates=["message", "callback_query", "message_reaction"],
    )

    yield

    # Cleanup defensivo contra timeouts de red en hot-reload
    if scheduler_started:
        scheduler.shutdown()
    try:
        await bot_cs_app.bot.delete_webhook()
    except Exception as e:
        logger.warning(f"CS bot delete_webhook fallo (ignorado en shutdown): {e}")
    try:
        await bot_cs_app.shutdown()
    except Exception as e:
        logger.warning(f"CS bot shutdown fallo: {e}")
    try:
        await bot_am_app.bot.delete_webhook()
    except Exception as e:
        logger.warning(f"AM bot delete_webhook fallo (ignorado en shutdown): {e}")
    try:
        await bot_am_app.shutdown()
    except Exception as e:
        logger.warning(f"AM bot shutdown fallo: {e}")
    await close_pool()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "ok", "scheduler_enabled": _is_scheduler_enabled()}


@app.post("/webhook/deluxecs")
async def webhook_cs(request: Request):
    update = telegram.Update.de_json(await request.json(), bot_cs_app.bot)
    await bot_cs_app.process_update(update)
    return Response(status_code=200)


@app.post("/webhook/deluxeam")
async def webhook_am(request: Request):
    update = telegram.Update.de_json(await request.json(), bot_am_app.bot)
    await bot_am_app.process_update(update)
    return Response(status_code=200)
