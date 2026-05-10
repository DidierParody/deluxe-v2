import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log errors and notify the user so they don't see silence."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Ocurrió un error procesando tu mensaje. Por favor inténtalo de nuevo."
            )
        except Exception:
            pass
