from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from app.config import settings
from app.bots.common import handle_error
from app.bots.payment_flow import handle_payment_receipt
from app.llm.orchestrator import process_message

async def start_cs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Enviar saludo inicial, luego el orchestrator puede registrarlo o la tool se puede llamar en backend
    await update.message.reply_text("¡Bienvenido a Deluxe! Soy tu recepcionista virtual. ¿En qué te puedo ayudar?")

async def handle_message_cs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    telegram_id = update.message.from_user.id
    update_id = update.update_id
    
    # Process message via LLM Orchestrator
    response = await process_message(chat_id, telegram_id, "customer", text, update_id)
    await update.message.reply_text(response)

def create_bot_cs() -> Application:
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN_CS).build()
    app.add_handler(CommandHandler("start", start_cs))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_cs))
    app.add_handler(MessageHandler(filters.PHOTO, handle_payment_receipt))
    app.add_error_handler(handle_error)
    return app
