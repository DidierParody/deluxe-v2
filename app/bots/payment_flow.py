from telegram import Update, ReactionTypeEmoji, InputFile
from telegram.ext import ContextTypes
from app.db.pool import get_connection
import app.bot_registry as bot_registry
import logging
import io

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PASO 1: Cliente envía foto del comprobante → se reenvía a TODOS los admins
# ─────────────────────────────────────────────────────────────────────────────
async def handle_payment_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    El cliente envió una foto como comprobante de pago.
    1. Se busca su orden pendiente más reciente.
    2. Se registra el pago en la BD.
    3. Se envía el comprobante a todos los admins registrados vía el bot AM.
    4. Se guarda en system.admin_payment_msgs el message_id de cada envío
       para poder rastrear la reacción posterior de cualquier admin.
    """
    telegram_id = update.message.from_user.id
    photo_file_id = update.message.photo[-1].file_id

    async with get_connection() as conn:
        # Buscar la orden pendiente más reciente del cliente
        order = await conn.fetchrow("""
            SELECT o.id, o.total
            FROM transactions.orders o
            JOIN core.users u ON u.id = o.user_id
            WHERE u.telegram_id = $1 AND o.status = 'pending'
            ORDER BY o.created_at DESC LIMIT 1
        """, telegram_id)

        if not order:
            await update.message.reply_text("No tienes órdenes pendientes de pago en este momento.")
            return

        # Registrar el pago en BD
        await conn.execute("""
            INSERT INTO transactions.payments
                (payment_method_id, amount, order_id, status, voucher_url, reference_number)
            VALUES
                ((SELECT id FROM catalog.payment_methods LIMIT 1), $1, $2, 'pending', $3, $4)
        """, order['total'], order['id'], photo_file_id, photo_file_id)

        # Obtener todos los admins registrados
        admins = await conn.fetch("""
            SELECT telegram_id FROM core.users
            WHERE type_user_id = (SELECT id FROM catalog.type_users WHERE name = 'admin')
        """)

    if not admins:
        logger.warning("No hay admins registrados. El comprobante no pudo ser enviado.")
        await update.message.reply_text(
            "✅ Comprobante recibido. Nuestro equipo lo verificará y te confirmaremos en breve."
        )
        return

    # Obtener el bot CS para descargar el archivo (los file_ids son bot-especificos en Telegram)
    bot_cs_app = bot_registry.bot_cs_app
    bot_am_app = bot_registry.bot_am_app

    if bot_am_app is None or bot_cs_app is None:
        logger.error("Los bots no estan inicializados en el registry. Comprobante NO enviado a admins.")
        await update.message.reply_text("Comprobante recibido. Nuestro equipo lo verificara en breve.")
        return

    # Descargar la imagen usando el CS bot (unico que puede acceder a su propio file_id)
    try:
        tg_file = await bot_cs_app.bot.get_file(photo_file_id)
        file_bytes = await tg_file.download_as_bytearray()
        logger.info(f"Imagen del comprobante descargada correctamente ({len(file_bytes)} bytes)")
    except Exception as e:
        logger.error(f"Error al descargar la imagen via CS bot: {e}")
        await update.message.reply_text("Comprobante recibido. Nuestro equipo lo verificara en breve.")
        return

    caption = (
        f"Nuevo comprobante de pago\n"
        f"Orden ID: {order['id']}\n"
        f"Total: ${order['total']}\n"
        f"Cliente Telegram ID: {telegram_id}\n"
        f"Reacciona con thumbs-up a este mensaje para APROBAR el pago."
    )

    # Broadcast: enviar a cada admin individualmente re-subiendo los bytes
    async with get_connection() as conn:
        for admin in admins:
            admin_tid = admin['telegram_id']
            try:
                # Re-subir los bytes via AM bot (resuelve el problema de file_ids bot-especificos)
                sent = await bot_am_app.bot.send_photo(
                    chat_id=admin_tid,
                    photo=InputFile(io.BytesIO(bytes(file_bytes)), filename="voucher.jpg"),
                    caption=caption
                )
                # Registrar el message_id en la tabla de rastreo
                await conn.execute("""
                    INSERT INTO system.admin_payment_msgs
                        (order_id, admin_telegram_id, message_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (admin_telegram_id, message_id) DO NOTHING
                """, order['id'], admin_tid, sent.message_id)

                logger.info(
                    f"Comprobante de orden {order['id']} enviado al admin {admin_tid} "
                    f"(msg_id={sent.message_id})"
                )
            except Exception as e:
                logger.error(f"Error al enviar comprobante al admin {admin_tid}: {e}")

    await update.message.reply_text(
        "Comprobante recibido. Nuestro equipo lo verificara y te confirmaremos en breve. Gracias!"
    )


# ─────────────────────────────────────────────────────────────────────────────
# PASO 2: Cualquier admin reacciona con 👍 → se aprueba la orden
# ─────────────────────────────────────────────────────────────────────────────
async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Un admin reaccionó con 👍 a un mensaje del bot AM en su DM.
    1. Verifica que la reacción sea 👍 y que el actor sea admin en la BD.
    2. Busca la orden correspondiente en system.admin_payment_msgs usando
       (message_id + admin_telegram_id).
    3. Aprueba la orden: activa tickets, confirma reservas, verifica pago.
    4. Notifica al cliente y edita el mensaje en el DM del admin que aprobó.
    5. Elimina los registros de la tabla de rastreo para limpiar.
    """
    reaction = update.message_reaction
    if not reaction:
        return

    # Solo procesar reacciones añadidas (no eliminadas)
    new_reactions = reaction.new_reaction
    if not new_reactions:
        return

    # Verificar si alguna reacción nueva es 👍
    is_thumbsup = any(
        isinstance(r, ReactionTypeEmoji) and r.emoji == "👍"
        for r in new_reactions
    )
    if not is_thumbsup:
        return

    reactor_id = reaction.user.id
    message_id = reaction.message_id

    async with get_connection() as conn:
        # Verificar que quien reaccionó sea admin
        is_admin = await conn.fetchrow("""
            SELECT id FROM core.users
            WHERE telegram_id = $1
              AND type_user_id = (SELECT id FROM catalog.type_users WHERE name = 'admin')
        """, reactor_id)

        if not is_admin:
            logger.warning(f"Reacción 👍 ignorada: {reactor_id} no es admin.")
            return

        # Buscar la orden por (message_id enviado a este admin específico)
        msg_record = await conn.fetchrow("""
            SELECT order_id FROM system.admin_payment_msgs
            WHERE admin_telegram_id = $1 AND message_id = $2
        """, reactor_id, message_id)

        if not msg_record:
            logger.warning(
                f"No se encontró orden para admin {reactor_id} / msg {message_id}."
            )
            return

        order_id = msg_record['order_id']

        async with conn.transaction():
            # Verificar que la orden siga pendiente (evitar doble aprobación)
            order = await conn.fetchrow(
                "SELECT id, user_id FROM transactions.orders WHERE id = $1 AND status = 'pending' FOR UPDATE",
                order_id
            )
            if not order:
                logger.info(f"Orden {order_id} ya fue procesada anteriormente. Ignorando.")
                return

            # Activar tickets
            await conn.execute("""
                UPDATE transactions.tickets
                SET ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'active')
                WHERE id IN (
                    SELECT ticket_id FROM transactions.order_details
                    WHERE order_id = $1 AND ticket_id IS NOT NULL
                )
            """, order_id)

            # Confirmar reservas
            await conn.execute("""
                UPDATE transactions.reservations
                SET reservation_state_id = (SELECT id FROM catalog.reservation_states WHERE name = 'confirmed')
                WHERE id IN (
                    SELECT reservation_id FROM transactions.order_details
                    WHERE order_id = $1 AND reservation_id IS NOT NULL
                )
            """, order_id)

            # Verificar el pago
            await conn.execute(
                "UPDATE transactions.payments SET status = 'verified' WHERE order_id = $1 AND status = 'pending'",
                order_id
            )

            # Aprobar la orden
            await conn.execute(
                "UPDATE transactions.orders SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                order_id
            )

            # Limpiar registros de rastreo para esta orden
            await conn.execute(
                "DELETE FROM system.admin_payment_msgs WHERE order_id = $1",
                order_id
            )

        logger.info(f"✅ Orden {order_id} APROBADA por admin {reactor_id}")

        # Obtener todos los admin_telegram_ids que recibieron este comprobante
        # (ya eliminados, así que guardamos el user_id antes de borrar)
        user = await conn.fetchrow(
            "SELECT telegram_id FROM core.users WHERE id = $1", order['user_id']
        )

    # Notificar al cliente via bot CS
    if user:
        bot_cs_app = bot_registry.bot_cs_app
        try:
            await bot_cs_app.bot.send_message(
                chat_id=user['telegram_id'],
                text=(
                    f"✅ ¡Tu pago para la orden `{order_id}` ha sido *aprobado*!\n\n"
                    f"Ya tienes acceso confirmado. ¡Nos vemos en Deluxe! 🎉"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error al notificar al cliente {user['telegram_id']}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Fallback: botón inline (deprecado, se mantiene por compatibilidad)
# ─────────────────────────────────────────────────────────────────────────────
async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption="⚠️ Este método está deprecado. Usa la reacción 👍 para aprobar pagos."
    )
