"""Provider-independent speech-to-text. Implementations return text or raise STTError with a stable code
that is safe to show to the user. Audio and transcripts are never logged here."""
import ipaddress
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


class STTError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class SpeechToText(Protocol):
    name: str
    processing: str  # "local": audio stays on this machine/network; "cloud": it is sent to a third party

    def transcribe(self, audio: bytes, *, mime: str, ext: str, language: str | None, prompt: str | None) -> str: ...


_LOCAL_NAMES = {"localhost", "host.docker.internal", "gateway.docker.internal"}


def infer_processing(base_url: str, override: str = "") -> str:
    """'local' for loopback/private/single-label hosts (a sibling container), otherwise 'cloud'."""
    if override in ("local", "cloud"):
        return override
    host = (urlparse(base_url).hostname or "").lower()
    if host in _LOCAL_NAMES or host.endswith(".local") or host.endswith(".internal") or ("." not in host and host):
        return "local"
    try:
        ip = ipaddress.ip_address(host)
        return "local" if ip.is_private or ip.is_loopback else "cloud"
    except ValueError:
        return "cloud"


class OpenAICompatSTT:
    """Any server implementing POST {base}/audio/transcriptions (faster-whisper-server, whisper.cpp server, OpenAI-style hosts)."""

    def __init__(self, base_url: str, model: str, api_key: str, timeout: int, processing: str):
        self.base_url, self.model, self.api_key, self.timeout = base_url.rstrip("/"), model, api_key, timeout
        self.name, self.processing = f"stt:{model}", processing

    def transcribe(self, audio, *, mime, ext, language, prompt):
        data = {"model": self.model, "response_format": "json", "temperature": "0"}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            r = httpx.post(f"{self.base_url}/audio/transcriptions", data=data, headers=headers,
                           files={"file": (f"dictation.{ext}", audio, mime)}, timeout=httpx.Timeout(self.timeout))
        except httpx.TimeoutException as exc:
            raise STTError("timeout", "The speech service took too long to respond. Try a shorter recording.") from exc
        except httpx.HTTPError as exc:
            raise STTError("provider_unavailable", "The speech service could not be reached.") from exc
        if r.status_code in (401, 403):
            raise STTError("provider_auth", "The speech service rejected our credentials. Ask an admin to check the configuration.")
        if r.status_code == 413:
            raise STTError("too_large", "The speech service says this recording is too large.")
        if r.status_code in (400, 415, 422):
            raise STTError("unsupported_format", "The speech service could not read this audio format.")
        if r.status_code >= 400:
            raise STTError("provider_error", f"The speech service failed (HTTP {r.status_code}).")
        try:
            text = r.json()["text"]
        except (ValueError, KeyError, TypeError) as exc:
            raise STTError("provider_error", "The speech service sent an unexpected reply.") from exc
        if not isinstance(text, str):
            raise STTError("provider_error", "The speech service sent an unexpected reply.")
        return text


class FakeSTT:
    """Deterministic stand-in for tests/demos. The audio bytes steer it: b"FAKE:<text>" returns that text,
    b"FAKE_FAIL" / b"FAKE_SLOW" / b"FAKE_EMPTY" simulate a provider error, a timeout and silence."""
    name, processing = "fake", "local"
    calls: list[dict] = []

    def transcribe(self, audio, *, mime, ext, language, prompt):
        FakeSTT.calls.append({"mime": mime, "ext": ext, "language": language, "prompt": prompt, "bytes": len(audio)})
        if b"FAKE_FAIL" in audio:
            raise STTError("provider_error", "The speech service failed (HTTP 500).")
        if b"FAKE_SLOW" in audio:
            raise STTError("timeout", "The speech service took too long to respond. Try a shorter recording.")
        if b"FAKE_EMPTY" in audio:
            return ""
        i = audio.find(b"FAKE:")
        return audio[i + 5:].decode("utf-8", errors="replace") if i >= 0 else "This is a test dictation."


_override: SpeechToText | None = None


def set_stt_override(stt: SpeechToText | None) -> None:
    global _override
    _override = stt


def get_stt() -> SpeechToText | None:
    """None means voice input is switched off."""
    if _override is not None:
        return _override
    s = get_settings()
    if s.stt_provider == "fake":
        return FakeSTT()
    if s.stt_provider == "openai_compat":
        return OpenAICompatSTT(s.stt_base_url, s.stt_model, s.stt_api_key, s.stt_timeout_seconds,
                               infer_processing(s.stt_base_url, s.stt_processing))
    return None
