import json
import logging
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.cache.redis_client import get_redis
from app.config import settings
from app.llm.session_memory import filter_session_patch

logger = logging.getLogger(__name__)

SENSITIVE_FIELD_MARKERS = (
    "id",
    "telegram",
    "voucher",
    "reference",
    "email",
    "phone",
    "token",
    "password",
)


class ConversationStore:
    def __init__(self):
        self._local_messages: Dict[str, Dict[str, Any]] = {}
        self._local_sessions: Dict[str, Dict[str, Any]] = {}

    async def load_conversation(self, role: str, chat_id: int) -> List[Dict[str, Any]]:
        key = self._messages_key(role, chat_id)
        ttl_seconds = self._ttl_for_role(role)

        if settings.REDIS_MEMORY_ENABLED:
            redis = await get_redis()
            if redis is not None:
                try:
                    payloads = await redis.lrange(key, 0, -1)
                    if payloads:
                        await redis.expire(key, ttl_seconds)
                    return [self._deserialize_message(payload) for payload in payloads]
                except Exception as exc:
                    logger.warning(f"Fallo al leer memoria conversacional desde Redis. Se usa fallback local. Error: {exc}")

        self._cleanup_local_messages()
        cached = self._local_messages.get(key)
        if not cached:
            return []
        cached["expires_at"] = datetime.now() + timedelta(seconds=ttl_seconds)
        return deepcopy(cached["messages"])

    async def append_messages(self, role: str, chat_id: int, messages: List[Dict[str, Any]]) -> None:
        if not messages:
            return

        sanitized_messages = [self._sanitize_message(message) for message in messages]
        key = self._messages_key(role, chat_id)
        ttl_seconds = self._ttl_for_role(role)

        if settings.REDIS_MEMORY_ENABLED:
            redis = await get_redis()
            if redis is not None:
                try:
                    serialized = [json.dumps(message, ensure_ascii=False) for message in sanitized_messages]
                    await redis.rpush(key, *serialized)
                    await redis.ltrim(key, -settings.REDIS_HISTORY_MAX_MESSAGES, -1)
                    await redis.expire(key, ttl_seconds)
                    return
                except Exception as exc:
                    logger.warning(f"Fallo al escribir memoria conversacional en Redis. Se usa fallback local. Error: {exc}")

        self._cleanup_local_messages()
        cached = self._local_messages.setdefault(
            key,
            {"messages": [], "expires_at": datetime.now() + timedelta(seconds=ttl_seconds)},
        )
        cached["messages"].extend(sanitized_messages)
        cached["messages"] = cached["messages"][-settings.REDIS_HISTORY_MAX_MESSAGES :]
        cached["expires_at"] = datetime.now() + timedelta(seconds=ttl_seconds)

    async def load_session(self, role: str, chat_id: int) -> Dict[str, Any]:
        key = self._session_key(role, chat_id)
        ttl_seconds = self._ttl_for_role(role)

        if settings.REDIS_MEMORY_ENABLED:
            redis = await get_redis()
            if redis is not None:
                try:
                    payload = await redis.get(key)
                    if payload:
                        await redis.expire(key, ttl_seconds)
                        return filter_session_patch(json.loads(payload))
                    return {}
                except Exception as exc:
                    logger.warning(f"Fallo al leer sesion desde Redis. Se usa fallback local. Error: {exc}")

        self._cleanup_local_sessions()
        cached = self._local_sessions.get(key)
        if not cached:
            return {}
        cached["expires_at"] = datetime.now() + timedelta(seconds=ttl_seconds)
        return deepcopy(cached["session"])

    async def merge_session(self, role: str, chat_id: int, patch: Dict[str, Any]) -> None:
        filtered_patch = filter_session_patch(patch)
        if not filtered_patch:
            return

        key = self._session_key(role, chat_id)
        ttl_seconds = self._ttl_for_role(role)

        if settings.REDIS_MEMORY_ENABLED:
            redis = await get_redis()
            if redis is not None:
                try:
                    current = await self.load_session(role, chat_id)
                    current.update(filtered_patch)
                    await redis.set(key, json.dumps(current, ensure_ascii=False), ex=ttl_seconds)
                    return
                except Exception as exc:
                    logger.warning(f"Fallo al escribir sesion en Redis. Se usa fallback local. Error: {exc}")

        self._cleanup_local_sessions()
        cached = self._local_sessions.setdefault(
            key,
            {"session": {}, "expires_at": datetime.now() + timedelta(seconds=ttl_seconds)},
        )
        cached["session"].update(filtered_patch)
        cached["expires_at"] = datetime.now() + timedelta(seconds=ttl_seconds)

    async def clear_memory(self, role: str, chat_id: int) -> None:
        message_key = self._messages_key(role, chat_id)
        session_key = self._session_key(role, chat_id)

        if settings.REDIS_MEMORY_ENABLED:
            redis = await get_redis()
            if redis is not None:
                try:
                    await redis.delete(message_key, session_key)
                except Exception as exc:
                    logger.warning(f"Fallo al limpiar memoria en Redis. Se intentara limpieza local. Error: {exc}")

        self._local_messages.pop(message_key, None)
        self._local_sessions.pop(session_key, None)

    def _messages_key(self, role: str, chat_id: int) -> str:
        return f"conv:{role}:{chat_id}:messages"

    def _session_key(self, role: str, chat_id: int) -> str:
        return f"conv:{role}:{chat_id}:session"

    def _ttl_for_role(self, role: str) -> int:
        minutes = (
            settings.REDIS_MEMORY_TTL_ADMIN_MINUTES
            if role == "admin"
            else settings.REDIS_MEMORY_TTL_CUSTOMER_MINUTES
        )
        return max(minutes, 1) * 60

    def _deserialize_message(self, payload: str) -> Dict[str, Any]:
        try:
            message = json.loads(payload)
            if isinstance(message, dict):
                return message
        except Exception:
            logger.warning("Se ignoro un mensaje invalido almacenado en memoria conversacional.")
        return {"role": "assistant", "content": ""}

    def _sanitize_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = {"role": message.get("role", "assistant")}

        content = message.get("content")
        if content is not None:
            sanitized["content"] = self._sanitize_value(content)

        if message.get("name"):
            sanitized["name"] = message["name"]

        if message.get("tool_call_id"):
            sanitized["tool_call_id"] = self._truncate_text(str(message["tool_call_id"]), max_chars=80)

        if message.get("tool_calls"):
            sanitized["tool_calls"] = [
                {
                    "id": self._truncate_text(str(tool_call.get("id", tool_call.get("name", "tool_call"))), max_chars=80),
                    "name": tool_call.get("name", "tool_call"),
                    "arguments": self._sanitize_value(tool_call.get("arguments", {})),
                }
                for tool_call in message["tool_calls"]
            ]

        return sanitized

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._truncate_text(value)

        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value[:10]]

        if isinstance(value, dict):
            sanitized: Dict[str, Any] = {}
            for key, nested_value in value.items():
                lowered_key = key.lower()
                if any(marker in lowered_key for marker in SENSITIVE_FIELD_MARKERS):
                    continue
                sanitized[key] = self._sanitize_value(nested_value)
            return sanitized

        return value

    def _truncate_text(self, text: str, max_chars: int = 500) -> str:
        compact = " ".join(text.split())
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 3] + "..."

    def _cleanup_local_messages(self):
        now = datetime.now()
        expired_keys = [
            key
            for key, payload in self._local_messages.items()
            if payload["expires_at"] <= now
        ]
        for key in expired_keys:
            del self._local_messages[key]

    def _cleanup_local_sessions(self):
        now = datetime.now()
        expired_keys = [
            key
            for key, payload in self._local_sessions.items()
            if payload["expires_at"] <= now
        ]
        for key in expired_keys:
            del self._local_sessions[key]


conversation_store = ConversationStore()
