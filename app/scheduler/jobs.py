import logging
from app.db.pool import get_connection

logger = logging.getLogger(__name__)


async def finalizar_eventos_expirados():
    """Marks events whose end_time has passed as finished."""
    try:
        async with get_connection() as conn:
            await conn.execute(
                """
                UPDATE core.events
                SET event_state_id = (SELECT id FROM catalog.event_states WHERE name = 'finished')
                WHERE event_state_id = (SELECT id FROM catalog.event_states WHERE name = 'ongoing')
                  AND end_time <= CURRENT_TIMESTAMP
                """
            )
    except Exception as exc:
        logger.error(f"finalizar_eventos_expirados error: {exc}")


async def liberar_mesas_expiradas():
    """Releases tables whose reservations have expired and marks reservations as completed."""
    try:
        async with get_connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE core.dico_tables
                    SET table_state_id = (SELECT id FROM catalog.table_states WHERE name = 'available')
                    WHERE id IN (
                        SELECT table_id FROM transactions.reservations
                        WHERE expires_at < CURRENT_TIMESTAMP
                          AND expires_at IS NOT NULL
                          AND reservation_state_id = (
                              SELECT id FROM catalog.reservation_states WHERE name = 'confirmed'
                          )
                    )
                    """
                )
                await conn.execute(
                    """
                    UPDATE transactions.reservations
                    SET reservation_state_id = (SELECT id FROM catalog.reservation_states WHERE name = 'completed')
                    WHERE expires_at < CURRENT_TIMESTAMP
                      AND expires_at IS NOT NULL
                      AND reservation_state_id = (
                          SELECT id FROM catalog.reservation_states WHERE name = 'confirmed'
                      )
                    """
                )
    except Exception as exc:
        logger.error(f"liberar_mesas_expiradas error: {exc}")
