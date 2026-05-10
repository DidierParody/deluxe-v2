"""
Unit tests for ticket purchase race condition fix.
Verifies that the SQL query merges the COUNT within the FOR UPDATE scope.
"""
import re
import inspect
import pytest
from unittest.mock import patch

with patch.dict("os.environ", {
    "DATABASE_URL": "postgresql://fake",
    "TELEGRAM_BOT_TOKEN_CS": "fake",
    "TELEGRAM_BOT_TOKEN_AM": "fake",
    "WEBHOOK_BASE_URL": "https://fake.example.com",
    "NVIDIA_API_KEY": "fake",
}):
    from app.agents.tools.ticket_tools import comprar_tickets


def test_comprar_tickets_uses_single_query_for_lock_and_count():
    """
    The race-condition fix requires that the COUNT of sold tickets
    happens inside the same SELECT ... FOR UPDATE query, not in a
    separate query after the lock is acquired.
    """
    source = inspect.getsource(comprar_tickets.func)

    # The fixed query contains a subquery COUNT inside the FOR UPDATE SELECT
    assert "FOR UPDATE" in source, "Must use FOR UPDATE to lock the ticket type row"

    # The subquery that counts sold tickets must appear before FOR UPDATE
    for_update_pos = source.index("FOR UPDATE")
    count_pos = source.index("SELECT COUNT(*)")
    assert count_pos < for_update_pos, (
        "COUNT(*) subquery must appear inside the SELECT...FOR UPDATE statement, "
        "not in a separate query after the lock."
    )


def test_comprar_tickets_uses_transaction():
    """All ticket purchases must be wrapped in a DB transaction."""
    source = inspect.getsource(comprar_tickets.func)
    assert "conn.transaction()" in source, "comprar_tickets must use a DB transaction"


def test_ver_tickets_disponibles_filters_cancelled():
    """Available ticket count must exclude cancelled tickets."""
    from app.agents.tools.ticket_tools import ver_tickets_disponibles
    source = inspect.getsource(ver_tickets_disponibles.func)
    assert "cancelled" in source.lower(), "Query must exclude cancelled tickets from count"
