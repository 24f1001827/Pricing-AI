from core.config import LLM_PROVIDER, GROQ_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY
from core.logger import get_logger
import os
import threading
import time
import random
from typing import Any

logger = get_logger(__name__)


class RateLimitedLLM:
    """Wraps a provider LLM object and enforces:
    - simple token-bucket style rate limit (calls per minute)
    - concurrency limit (max concurrent invoke calls)
    - retries with exponential backoff and jitter on transient errors
    Delegates attribute access to the underlying LLM.
    """

    def __init__(self, llm_impl: Any, calls_per_minute: int = 60, max_concurrency: int = 4, max_retries: int = 3):
        self._llm = llm_impl
        self.calls_per_minute = max(1, calls_per_minute)
        self._lock = threading.Lock()
        self._tokens = self.calls_per_minute
        self._last_refill = time.time()
        self._refill_interval = 60.0
        self._semaphore = threading.BoundedSemaphore(value=max_concurrency)
        self._max_retries = max_retries

    def _refill(self):
        now = time.time()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        add = int((elapsed / self._refill_interval) * self.calls_per_minute)
        if add > 0:
            with self._lock:
                self._tokens = min(self.calls_per_minute, self._tokens + add)
                self._last_refill = now

    def _acquire_token(self, timeout: float = None) -> bool:
        end = None if timeout is None else time.time() + timeout
        while True:
            self._refill()
            with self._lock:
                if self._tokens > 0:
                    self._tokens -= 1
                    return True
            if end and time.time() > end:
                return False
            time.sleep(0.05)

    def invoke(self, *args, timeout: float = 30.0, **kwargs):
        acquired = self._semaphore.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError("LLM concurrency limit reached")
        try:
            if not self._acquire_token(timeout=timeout):
                raise TimeoutError("LLM rate limit exceeded (no tokens available)")

            attempt = 0
            while True:
                try:
                    attempt += 1
                    return self._llm.invoke(*args, **kwargs)
                except Exception as e:
                    if attempt > self._max_retries:
                        logger.error(f"LLM invoke failed after {attempt} attempts: {str(e)}")
                        raise
                    backoff = (2 ** (attempt - 1)) + random.uniform(0, 1)
                    logger.warning(f"LLM invoke failed (attempt {attempt}), retrying after {backoff:.2f}s: {str(e)}")
                    time.sleep(backoff)
        finally:
            try:
                self._semaphore.release()
            except ValueError:
                pass

    def bind_tools(self, *args, **kwargs):
        bound = self._llm.bind_tools(*args, **kwargs)
        # Use same rate limits for the bound object
        return RateLimitedLLM(bound, calls_per_minute=self.calls_per_minute, max_concurrency=4, max_retries=self._max_retries)
    
    def with_structured_output(self, *args, **kwargs):
        bound = self._llm.with_structured_output(*args, **kwargs)
        return RateLimitedLLM(
            bound,
            calls_per_minute=self.calls_per_minute,
            max_concurrency=4,
            max_retries=self._max_retries
        )

    def __getattr__(self, item):
        return getattr(self._llm, item)


def _create_provider_llm():
    logger.info(f"Initializing LLM provider: {LLM_PROVIDER}")

    if LLM_PROVIDER == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)
    elif LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model="gemini-2.5-flash", api_key=GOOGLE_API_KEY)
    elif LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY)
    elif LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-sonnet-4-6", api_key=ANTHROPIC_API_KEY)
    else:
        logger.warning(f"Unknown provider {LLM_PROVIDER}, falling back to Groq")
        from langchain_groq import ChatGroq
        return ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)


_llm_instance = None
_validation_llm_instance = None

def get_llm():
    global _llm_instance
    if _llm_instance is None:
        calls_per_minute = int(os.getenv("LLM_RATE_LIMIT_PER_MINUTE", "60"))
        max_concurrency = int(os.getenv("LLM_MAX_CONCURRENCY", "4"))
        max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))
        provider = _create_provider_llm()
        _llm_instance = RateLimitedLLM(provider, calls_per_minute=calls_per_minute, max_concurrency=max_concurrency, max_retries=max_retries)
        logger.info(f"Wrapped LLM with rate limit={calls_per_minute}/min, concurrency={max_concurrency}, retries={max_retries}")
    return _llm_instance


def get_validation_llm():
    """Use smallest model of configured provider for simple tasks"""
    global _validation_llm_instance
    if _validation_llm_instance is None:
        if LLM_PROVIDER == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            base = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY)
        elif LLM_PROVIDER == "groq":
            from langchain_groq import ChatGroq
            base = ChatGroq(model="llama-3.1-8b-instant", api_key=GROQ_API_KEY)
        elif LLM_PROVIDER == "openai":
            from langchain_openai import ChatOpenAI
            base = ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY)
        elif LLM_PROVIDER == "anthropic":
            from langchain_anthropic import ChatAnthropic
            base = ChatAnthropic(model="claude-sonnet-4-6", api_key=ANTHROPIC_API_KEY)
        else:
            base = _create_provider_llm()
        calls_per_minute = int(os.getenv("LLM_RATE_LIMIT_PER_MINUTE", "60"))
        max_concurrency = int(os.getenv("LLM_MAX_CONCURRENCY", "4"))
        max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))
        _validation_llm_instance = RateLimitedLLM(base, calls_per_minute=calls_per_minute, max_concurrency=max_concurrency, max_retries=max_retries)
    return _validation_llm_instance 
    