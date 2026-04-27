from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, MessageReactionHandler
from app.config import settings
from app.bots.common import handle_error
from app.bots.payment_flow import handle_admin_callback, handle_reaction
from app.llm.orchestrator import process_message
from app.db.pool import get_connection

async def is_admin(telegram_id: int) -> bool:
    async with get_connection() as conn:
        row = await conn.fetchrow("""
            SELECT id FROM core.users 
            WHERE telegram_id = $1 AND type_user_id = (SELECT id FROM catalog.type_users WHERE name = 'admin')
        """, telegram_id)
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
            f"Para obtener acceso, por favor entrega el siguiente código a un administrador del sistema:\n\n"
            f"🔑 Código: `{code}`\n"
            f"🆔 Tu Telegram ID: `{telegram_id}`\n\n"
            f"Este código expira en 5 minutos. Una vez que te den acceso, vuelve a escribir /start.",
            parse_mode="Markdown"
        )

async def handle_message_am(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    if not await is_admin(telegram_id):
        await update.message.reply_text("No tienes permisos de administrador.")
        return
        
    text = update.message.text
    chat_id = update.effective_chat.id
    update_id = update.update_id
    
    response = await process_message(chat_id, telegram_id, "admin", text, update_id)
    await update.message.reply_text(response, parse_mode="Markdown")

def create_bot_am() -> Application:
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN_AM).build()
    app.add_handler(CommandHandler("start", start_am))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_am))
    app.add_handler(CallbackQueryHandler(handle_admin_callback))
    # Handler de reacciones 👍 para aprobar pagos
    app.add_handler(MessageReactionHandler(handle_reaction))
    app.add_error_handler(handle_error)
    return app
