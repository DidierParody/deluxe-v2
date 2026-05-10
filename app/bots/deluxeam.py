import logging
from langchain_core.messages import HumanMessage, AIMessage
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    MessageReactionHandler,
    filters,
)

import app.bot_registry as bot_registry
from app.bots.common import handle_error
from app.bots.payment_flow import handle_admin_callback, handle_reaction
from app.config import settings
from app.db.pool import get_connection
from app.idempotency.store import idempotency_store
from app.llm.session_memory import derive_session_patch

logger = logging.getLogger(__name__)


async def is_admin(telegram_id: int) -> bool:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id FROM core.users
            WHERE telegram_id = $1
              AND type_user_id = (SELECT id FROM catalog.type_users WHERE name = 'admin')
            """,
            telegram_id,
        )
        return row is not None


async def start_am(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    if await is_admin(telegram_id):
        await update.message.reply_text("¡Bienvenido Admin Deluxe! ¿Qué deseas gestionar hoy?")
    else:
        from app.auth.pairing import generate_pairing_code
        code = await generate_pairing_code(telegram_id)
        await update.message.reply_text(
            f"⛔ Acceso denegado.\n\n"
            f"Entrega este código a un administrador del sistema:\n\n"
            f"🔑 Código: `{code}`\n"
            f"🆔 Tu Telegram ID: `{telegram_id}`\n\n"
            f"Expira en 5 minutos. Una vez habilitado, escribe /start nuevamente.",
            parse_mode="Markdown",
        )


async def handle_message_am(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    if not await is_admin(telegram_id):
        await update.message.reply_text("No tienes permisos de administrador.")
        return

    text = update.message.text
    chat_id = update.effective_chat.id
    update_id = update.update_id

    cached = await idempotency_store.get(update_id)
    if cached is not None:
        await update.message.reply_text(cached, parse_mode="Markdown")
        return

    patch = derive_session_patch("admin", text)
    state = {
        "messages": [HumanMessage(content=text)],
        "telegram_id": telegram_id,
        "chat_id": chat_id,
        "role": "admin",
        "next_agent": None,
        "update_id": update_id,
        **patch,
    }

    graph = bot_registry.graph
    result = await graph.ainvoke(
        state,
        config={"configurable": {"thread_id": f"admin:{chat_id}"}},
    )

    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
    response = ai_messages[-1].content if ai_messages else "Ocurrió un error, intenta de nuevo."

    await idempotency_store.set(update_id, response)
    await update.message.reply_text(response, parse_mode="Markdown")


def create_bot_am() -> Application:
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN_AM).build()
    app.add_handler(CommandHandler("start", start_am))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_am))
    app.add_handler(CallbackQueryHandler(handle_admin_callback))
    app.add_handler(MessageReactionHandler(handle_reaction))
    app.add_error_handler(handle_error)
    return app
