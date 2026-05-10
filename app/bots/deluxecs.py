import logging
from langchain_core.messages import HumanMessage, AIMessage
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import app.bot_registry as bot_registry
from app.bots.common import handle_error
from app.bots.payment_flow import handle_payment_receipt
from app.config import settings
from app.idempotency.store import idempotency_store
from app.llm.session_memory import derive_session_patch

logger = logging.getLogger(__name__)


async def start_cs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Bienvenido a Deluxe! Soy tu recepcionista virtual. ¿En qué te puedo ayudar?"
    )


async def handle_message_cs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    telegram_id = update.message.from_user.id
    update_id = update.update_id

    cached = await idempotency_store.get(update_id)
    if cached is not None:
        await update.message.reply_text(cached)
        return

    patch = derive_session_patch("customer", text)
    state = {
        "messages": [HumanMessage(content=text)],
        "telegram_id": telegram_id,
        "chat_id": chat_id,
        "role": "customer",
        "next_agent": None,
        "update_id": update_id,
        **patch,
    }

    graph = bot_registry.graph
    result = await graph.ainvoke(
        state,
        config={"configurable": {"thread_id": str(chat_id)}},
    )

    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
    response = ai_messages[-1].content if ai_messages else "Ocurrió un error, intenta de nuevo."

    await idempotency_store.set(update_id, response)
    await update.message.reply_text(response)


def create_bot_cs() -> Application:
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN_CS).build()
    app.add_handler(CommandHandler("start", start_cs))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_cs))
    app.add_handler(MessageHandler(filters.PHOTO, handle_payment_receipt))
    app.add_error_handler(handle_error)
    return app
