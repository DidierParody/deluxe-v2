import re
from typing import Any

ALLOWED_SESSION_KEYS = {
    "active_flow",
    "event_name",
    "event_id",
    "party_size",
    "selected_table",
    "ticket_type",
    "quantity",
    "budget_hint",
    "last_user_intent",
}

FLOW_KEYWORDS = {
    "reservation": ("reserva", "mesa", "vip", "regular", "evento"),
    "tickets": ("ticket", "tickets", "boleta", "boletas", "entrada", "entradas"),
    "payment": ("pago", "pagar", "comprobante", "transferencia"),
    "admin": ("aprobar", "gestionar", "crear evento", "cerrar evento"),
}

TICKET_TYPES = ("general", "vip", "palco", "preventa")


def filter_session_patch(patch: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in patch.items()
        if key in ALLOWED_SESSION_KEYS and value not in (None, "", [], {})
    }


def derive_session_patch(role: str, text: str) -> dict[str, Any]:
    normalized = text.lower().strip()
    patch: dict[str, Any] = {}

    active_flow = _detect_active_flow(role, normalized)
    if active_flow:
        patch["active_flow"] = active_flow

    patch["last_user_intent"] = _extract_intent(normalized)

    event_name = _extract_event_name(text)
    if event_name:
        patch["event_name"] = event_name

    party_size = _extract_party_size(normalized)
    if party_size is not None:
        patch["party_size"] = party_size

    selected_table = _extract_selected_table(normalized)
    if selected_table is not None:
        patch["selected_table"] = selected_table

    quantity = _extract_quantity(normalized)
    if quantity is not None:
        patch["quantity"] = quantity

    ticket_type = _extract_ticket_type(normalized)
    if ticket_type:
        patch["ticket_type"] = ticket_type

    budget_hint = _extract_budget(normalized)
    if budget_hint:
        patch["budget_hint"] = budget_hint

    return filter_session_patch(patch)


def build_memory_prompt(session: dict[str, Any], has_recent_history: bool) -> str:
    snippets = []

    if has_recent_history:
        snippets.append(
            "Ya hubo intercambio reciente con este usuario. No vuelvas a presentarte como si fuera su primer mensaje."
        )

    active_flow = session.get("active_flow")
    if active_flow:
        snippets.append(f"Flujo activo actual: {active_flow}.")

    event_name = session.get("event_name")
    if event_name:
        snippets.append(f"Evento mencionado recientemente: {event_name}.")

    party_size = session.get("party_size")
    if party_size:
        snippets.append(f"Cantidad de personas recordada: {party_size}.")

    selected_table = session.get("selected_table")
    if selected_table:
        snippets.append(f"Mesa mencionada recientemente: {selected_table}.")

    ticket_type = session.get("ticket_type")
    if ticket_type:
        snippets.append(f"Tipo de ticket en contexto: {ticket_type}.")

    quantity = session.get("quantity")
    if quantity:
        snippets.append(f"Cantidad de tickets o items en contexto: {quantity}.")

    budget_hint = session.get("budget_hint")
    if budget_hint:
        snippets.append(f"Presupuesto mencionado por el usuario: {budget_hint}.")

    last_user_intent = session.get("last_user_intent")
    if last_user_intent:
        snippets.append(f"Ultima intencion detectada: {last_user_intent}.")

    if not snippets:
        return ""

    return "[MEMORIA DE SESION]\n" + "\n".join(f"- {snippet}" for snippet in snippets)


def _detect_active_flow(role: str, normalized: str) -> str:
    if role == "admin":
        return "admin"

    for flow, keywords in FLOW_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return flow
    return "general"


def _extract_intent(normalized: str) -> str:
    if any(keyword in normalized for keyword in ("reserv", "mesa")):
        return "reservar mesa"
    if any(keyword in normalized for keyword in ("ticket", "boleta", "entrada")):
        return "comprar tickets"
    if any(keyword in normalized for keyword in ("pago", "comprobante", "transferencia")):
        return "enviar pago"
    if any(keyword in normalized for keyword in ("horario", "hora", "cuando", "cuándo")):
        return "consultar horario"
    return "consulta general"


def _extract_event_name(text: str) -> str | None:
    quoted = re.search(r'["“](.+?)["”]', text)
    if quoted:
        return quoted.group(1).strip()

    event_match = re.search(
        r"(?:evento|fiesta)\s+([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ-]*(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ-]*){0,4})",
        text,
    )
    if event_match:
        return event_match.group(1).strip()
    return None


def _extract_party_size(normalized: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:personas|persona|amigos|amigas)", normalized)
    if match:
        return int(match.group(1))
    return None


def _extract_selected_table(normalized: str) -> int | None:
    match = re.search(r"(?:mesa|table)\s*(?:n(?:u|ú)mero\s*)?(\d+)", normalized)
    if match:
        return int(match.group(1))
    return None


def _extract_quantity(normalized: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:tickets|ticket|boletas|boleta|entradas|entrada)", normalized)
    if match:
        return int(match.group(1))
    if normalized.isdigit():
        return int(normalized)
    return None


def _extract_ticket_type(normalized: str) -> str | None:
    for ticket_type in TICKET_TYPES:
        if ticket_type in normalized:
            return ticket_type
    return None


def _extract_budget(normalized: str) -> str | None:
    match = re.search(r"(\$?\s?\d[\d\.\,]*)", normalized)
    if match and any(
        keyword in normalized
        for keyword in ("presupuesto", "tengo", "máximo", "maximo", "cuesta", "vale")
    ):
        return match.group(1).replace(" ", "")
    return None
