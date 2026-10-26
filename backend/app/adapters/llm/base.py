"""Provider-independent LLM interface. Every call returns schema-validated output or raises."""
import json
import re
import time
import uuid
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AIUsageRecord

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(Exception):
    """Model missing/unreachable/invalid output. Callers fall back to deterministic templates."""


class LLM(Protocol):
    name: str

    def complete_json(self, *, system: str, user: str, schema: type[T], max_tokens: int = 300) -> tuple[T, dict]: ...


def _extract_json(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return m.group(0) if m else text


class OllamaLLM:
    """Ollama / any OpenAI-compatible server (llama.cpp, vLLM, LM Studio)."""

    def __init__(self, base_url: str, model: str, timeout: int):
        self.base_url, self.model, self.timeout, self.name = base_url.rstrip("/"), model, timeout, f"ollama:{model}"

    def complete_json(self, *, system, user, schema, max_tokens=300):
        payload = {"model": self.model, "temperature": 0.2, "max_tokens": max_tokens,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": system + "\nReply with a single JSON object only."},
                                {"role": "user", "content": user}]}
        last: Exception | None = None
        for attempt in range(2):
            try:
                r = httpx.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout)
                r.raise_for_status()
                data = r.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                return schema.model_validate(json.loads(_extract_json(content))), {
                    "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc
            except (json.JSONDecodeError, ValidationError) as exc:
                last = exc
                payload["messages"].append({"role": "user", "content": "Your reply was not valid JSON for the schema. Return only valid JSON."})
        raise LLMUnavailable(f"invalid model output: {last}")


class FakeLLM:
    """Deterministic stand-in for tests/demos. `handler(schema, user) -> dict`."""
    name = "fake"

    def __init__(self, handler=None):
        self.handler, self.calls = handler, []

    def complete_json(self, *, system, user, schema, max_tokens=300):
        self.calls.append((system, user))
        if self.handler is None:
            raise LLMUnavailable("fake llm has no handler")
        return schema.model_validate(self.handler(schema, user)), {"prompt_tokens": len(user) // 4, "completion_tokens": 50}


_override: LLM | None = None


def set_llm_override(llm: LLM | None) -> None:
    global _override
    _override = llm


def get_llm() -> LLM | None:
    """None means 'templates only'."""
    if _override is not None:
        return _override
    s = get_settings()
    if s.llm_provider == "ollama":
        return OllamaLLM(s.llm_base_url, s.llm_model, s.llm_timeout_seconds)
    return None


def call_llm(db: Session, workspace_id: uuid.UUID | None, task: str, *, system: str, user: str,
             schema: type[T], max_tokens: int = 300) -> T:
    """Run an LLM task, record usage/latency/failure, raise LLMUnavailable on any problem."""
    llm = get_llm()
    if llm is None:
        raise LLMUnavailable("no LLM configured (templates only)")
    t0 = time.perf_counter()
    try:
        out, usage = llm.complete_json(system=system, user=user, schema=schema, max_tokens=max_tokens)
        ok, err = True, None
    except LLMUnavailable as exc:
        out, usage, ok, err = None, {}, False, str(exc)[:300]
    db.add(AIUsageRecord(workspace_id=workspace_id, task=task, model=llm.name, ok=ok, error=err,
                         latency_ms=int((time.perf_counter() - t0) * 1000),
                         prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens")))
    db.flush()
    if not ok:
        raise LLMUnavailable(err or "failed")
    return out  # type: ignore[return-value]
