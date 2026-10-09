"""
Shared LLM access: one OpenAI client (timeouts + retries), per-call usage/cost logging, and
request context (user / prep session) so usage can be attributed.

All agents call `chat_completion(agent=..., ...)` instead of creating their own client.
Errors from the OpenAI SDK propagate unchanged, so each agent keeps its own fallback handling.
"""

import contextvars
import logging
import time
import uuid as uuid_pkg
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

from app.config import settings

logger = logging.getLogger("app.llm")

# Request-scoped attribution, set by get_current_user and the session service.
current_user_id: contextvars.ContextVar[Optional[uuid_pkg.UUID]] = contextvars.ContextVar(
    "llm_user_id", default=None
)
current_session_id: contextvars.ContextVar[Optional[uuid_pkg.UUID]] = contextvars.ContextVar(
    "llm_session_id", default=None
)

# USD per 1M tokens (input, output). Update when OpenAI pricing changes; unknown models log cost=None.
MODEL_PRICES_PER_1M: Dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}

_client = None
_client_key: Optional[str] = None


class LLMUnavailableError(RuntimeError):
    """No API key configured or the OpenAI SDK could not be loaded."""


def get_client():
    """Process-wide AsyncOpenAI client (re-created if the API key changes)."""
    global _client, _client_key
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise LLMUnavailableError("OPENAI_API_KEY is not set.")
    if _client is None or _client_key != api_key:
        try:
            from openai import AsyncOpenAI
        except ImportError as e:  # pragma: no cover - dependency is installed
            raise LLMUnavailableError("openai package is not installed.") from e
        _client = AsyncOpenAI(
            api_key=api_key,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )
        _client_key = api_key
    return _client


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> Optional[float]:
    prices = MODEL_PRICES_PER_1M.get(model)
    if prices is None:
        # Dated snapshots (e.g. gpt-4o-mini-2024-07-18) share the base model's price.
        base = next((m for m in sorted(MODEL_PRICES_PER_1M, key=len, reverse=True) if model.startswith(m + "-")), None)
        prices = MODEL_PRICES_PER_1M.get(base) if base else None
    if prices is None:
        return None
    return round((prompt_tokens * prices[0] + completion_tokens * prices[1]) / 1_000_000, 6)


@dataclass
class UsageRecord:
    agent: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Optional[float]
    latency_ms: int
    success: bool
    user_id: Optional[uuid_pkg.UUID]
    session_id: Optional[uuid_pkg.UUID]
    error: Optional[str] = None


async def record_usage(record: UsageRecord) -> None:
    """Log the call and persist it to llm_usage. Never raises."""
    logger.info(
        "llm call agent=%s model=%s ok=%s latency_ms=%d tokens_in=%d tokens_out=%d cost_usd=%s user=%s session=%s%s",
        record.agent,
        record.model,
        record.success,
        record.latency_ms,
        record.prompt_tokens,
        record.completion_tokens,
        record.cost_usd,
        record.user_id,
        record.session_id,
        f" error={record.error}" if record.error else "",
    )
    if not settings.LLM_USAGE_TRACKING_ENABLED:
        return
    try:
        from app.database import SessionLocal
        from app.models import LLMUsage

        async with SessionLocal() as db:
            db.add(
                LLMUsage(
                    user_id=record.user_id,
                    session_id=record.session_id,
                    agent=record.agent,
                    model=record.model,
                    prompt_tokens=record.prompt_tokens,
                    completion_tokens=record.completion_tokens,
                    cost_usd=record.cost_usd,
                    latency_ms=record.latency_ms,
                    success=record.success,
                )
            )
            await db.commit()
    except Exception as e:  # usage tracking must never break a user request
        logger.warning("Could not persist LLM usage: %s", e)


def _usage_counts(usage: Any) -> tuple[int, int]:
    if usage is None:
        return 0, 0
    return int(getattr(usage, "prompt_tokens", 0) or 0), int(getattr(usage, "completion_tokens", 0) or 0)


async def chat_completion(*, agent: str, model: str, messages: List[Dict[str, Any]], **kwargs: Any):
    """chat.completions.create with shared client, timing, and usage/cost tracking.

    agent: short name of the caller (e.g. "session_qa.evaluate") used for cost breakdowns.
    Extra kwargs (temperature, response_format, ...) are passed through.
    """
    client = get_client()
    start = time.monotonic()
    user_id, session_id = current_user_id.get(), current_session_id.get()
    try:
        response = await client.chat.completions.create(model=model, messages=messages, **kwargs)
    except Exception as e:
        await record_usage(
            UsageRecord(
                agent=agent,
                model=model,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=None,
                latency_ms=int((time.monotonic() - start) * 1000),
                success=False,
                user_id=user_id,
                session_id=session_id,
                error=type(e).__name__,
            )
        )
        raise
    prompt_tokens, completion_tokens = _usage_counts(getattr(response, "usage", None))
    await record_usage(
        UsageRecord(
            agent=agent,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=estimate_cost_usd(model, prompt_tokens, completion_tokens),
            latency_ms=int((time.monotonic() - start) * 1000),
            success=True,
            user_id=user_id,
            session_id=session_id,
        )
    )
    return response


async def chat_completion_stream(
    *, agent: str, model: str, messages: List[Dict[str, Any]], **kwargs: Any
) -> AsyncIterator[str]:
    """Stream text deltas from chat.completions; records usage when the stream ends."""
    client = get_client()
    start = time.monotonic()
    user_id, session_id = current_user_id.get(), current_session_id.get()
    prompt_tokens = completion_tokens = 0
    success = False
    error: Optional[str] = None
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                prompt_tokens, completion_tokens = _usage_counts(chunk.usage)
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta = getattr(choices[0].delta, "content", None)
                if delta:
                    yield delta
        success = True
    except Exception as e:
        error = type(e).__name__
        raise
    finally:
        await record_usage(
            UsageRecord(
                agent=agent,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=estimate_cost_usd(model, prompt_tokens, completion_tokens) if success else None,
                latency_ms=int((time.monotonic() - start) * 1000),
                success=success,
                user_id=user_id,
                session_id=session_id,
                error=error,
            )
        )
