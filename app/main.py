from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.db.pool import init_pool, close_pool
from app.bots.deluxecs import create_bot_cs
from app.bots.deluxeam import create_bot_am
from app.scheduler.jobs import finalizar_eventos_expirados, liberar_mesas_expiradas
import app.bot_registry as bot_registry
import telegram
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instancia de bots (global scope)
bot_cs_app = create_bot_cs()
bot_am_app = create_bot_am()
scheduler = AsyncIOScheduler()

# Registrar en el registry compartido para evitar imports circulares
bot_registry.bot_cs_app = bot_cs_app
bot_registry.bot_am_app = bot_am_app

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar DB
    await init_pool()
    
    # Inicializar Scheduler
    scheduler.add_job(finalizar_eventos_expirados, 'interval', minutes=5)
    scheduler.add_job(liberar_mesas_expiradas, 'interval', minutes=10)
    scheduler.start()
    
    # Inicializar bots y webhooks
    await bot_cs_app.initialize()
    await bot_cs_app.bot.set_webhook(
        url=f"{settings.WEBHOOK_BASE_URL}/webhook/deluxecs",
        allowed_updates=["message", "callback_query"]
    )
    
    await bot_am_app.initialize()
    await bot_am_app.bot.set_webhook(
        url=f"{settings.WEBHOOK_BASE_URL}/webhook/deluxeam",
        allowed_updates=["message", "callback_query", "message_reaction"]
    )
    
    yield
    
    # Cleanup — defensivo contra timeouts de red en hot-reload
    scheduler.shutdown()
    try:
        await bot_cs_app.bot.delete_webhook()
    except Exception as e:
        logger.warning(f"CS bot delete_webhook falló (ignorado en shutdown): {e}")
    try:
        await bot_cs_app.shutdown()
    except Exception as e:
        logger.warning(f"CS bot shutdown falló: {e}")
    try:
        await bot_am_app.bot.delete_webhook()
    except Exception as e:
        logger.warning(f"AM bot delete_webhook falló (ignorado en shutdown): {e}")
    try:
        await bot_am_app.shutdown()
    except Exception as e:
        logger.warning(f"AM bot shutdown falló: {e}")
    await close_pool()

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

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
