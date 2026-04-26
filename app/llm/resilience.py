import logging
from tenacity import retry, wait_exponential_jitter, retry_if_exception_type, stop_after_attempt
from app.llm.base import LLMClient, LLMResponse
from app.llm.google_client import GoogleClient
from app.llm.groq_client import GroqClient
import google.genai.errors as google_errors
import groq

logger = logging.getLogger(__name__)

# Initialize clients lazily or directly
_google_client = None
_groq_client = None

def get_google_client():
    global _google_client
    if _google_client is None:
        _google_client = GoogleClient()
    return _google_client

def get_groq_client():
    global _groq_client
    if _groq_client is None:
        _groq_client = GroqClient()
    return _groq_client

# Define what errors to retry on for Google (e.g. Rate Limit 429)
def is_google_transient_error(exception):
    # Google GenAI raises APIError
    if isinstance(exception, google_errors.APIError):
        return exception.code in [429, 500, 503]
    return False

# Define what errors to retry on for Groq
def is_groq_transient_error(exception):
    if isinstance(exception, (groq.RateLimitError, groq.InternalServerError, groq.APIConnectionError)):
        return True
    return False

class RateLimitExhausted(Exception):
    pass

@retry(
    wait=wait_exponential_jitter(initial=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(Exception), # We will filter inside or rely on specific wrappers
    reraise=True
)
async def _attempt_google(messages, tools):
    try:
        logger.info("Attempting with Google Gemini...")
        return await get_google_client().chat(messages, tools)
    except Exception as e:
        if is_google_transient_error(e):
            logger.warning(f"Google API transient error: {e}. Retrying...")
            raise
        else:
            logger.error(f"Google API fatal error: {e}. Will fallback to Groq.")
            raise RateLimitExhausted("Google failed permanently or with non-retryable error")

@retry(
    wait=wait_exponential_jitter(initial=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(Exception),
    reraise=True
)
async def _attempt_groq(messages, tools):
    try:
        logger.info("Attempting with Groq Llama 3.3...")
        return await get_groq_client().chat(messages, tools)
    except Exception as e:
        if is_groq_transient_error(e):
            logger.warning(f"Groq API transient error: {e}. Retrying...")
            raise
        else:
            logger.error(f"Groq API fatal error: {e}.")
            raise RateLimitExhausted("Groq failed permanently or with non-retryable error")

async def call_with_resilience(messages, tools) -> LLMResponse:
    """
    Tries Google first. If it fails after retries, falls back to Groq.
    If both fail, returns a friendly error message as a text response.
    """
    try:
        return await _attempt_google(messages, tools)
    except Exception as e_google:
        logger.warning(f"Google primary failed completely: {e_google}. Falling back to Groq.")
        
        try:
            return await _attempt_groq(messages, tools)
        except Exception as e_groq:
            logger.error(f"Groq fallback also failed: {e_groq}. Both providers exhausted.")
            # Both failed. Return a graceful error to the user without raising an exception that kills the bot.
            return LLMResponse(text="⏳ Estamos experimentando una alta demanda en este momento y no pude procesar tu solicitud. Por favor, intenta de nuevo en unos segundos. 🙏")
