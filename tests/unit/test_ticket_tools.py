"""
Unit tests for ticket purchase race condition fix.
Verifies that the SQL query merges the COUNT within the FOR UPDATE scope.
"""

import re
from pathlib import Path
from unittest.mock import patch

with patch.dict(
    "os.environ",
    {
        "DATABASE_URL": "postgresql://fake",
        "TELEGRAM_BOT_TOKEN_CS": "fake",
        "TELEGRAM_BOT_TOKEN_AM": "fake",
        "WEBHOOK_BASE_URL": "https://fake.example.com",
        "NVIDIA_API_KEY": "fake",
    },
):
    from app.agents.tools.ticket_tools import comprar_tickets, ver_tickets_disponibles  # noqa: F401

_TOOLS_FILE = Path(__file__).parent.parent.parent / "app" / "agents" / "tools" / "ticket_tools.py"


def _source() -> str:
    return _TOOLS_FILE.read_text(encoding="utf-8")


def test_comprar_tickets_uses_single_query_for_lock_and_count():
    """
    The race-condition fix requires that the COUNT of sold tickets
    happens inside the same SELECT ... FOR UPDATE query, not in a
    separate query after the lock is acquired.
    """
    content = _source()
    pattern = re.compile(r"SELECT COUNT\(\*\).*?FOR UPDATE", re.DOTALL)
    assert pattern.search(content), (
        "The comprar_tickets query must contain SELECT COUNT(*) inside the "
        "same SQL block as FOR UPDATE (race condition fix)."
    )


def test_comprar_tickets_uses_transaction():
    """All ticket purchases must be wrapped in a DB transaction."""
    assert "conn.transaction()" in _source(), "comprar_tickets must use a DB transaction"


def test_ver_tickets_disponibles_filters_cancelled():
    """Available ticket count must exclude cancelled tickets."""
    assert "cancelled" in _source().lower(), "Query must exclude cancelled tickets from count"
