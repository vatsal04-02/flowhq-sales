"""Named safety tests for voice dictation: privacy, authentication, and 'dictation never acts on its own'."""
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.adapters.channels.base import MockAdapter
from app.adapters.llm.base import FakeLLM, set_llm_override
from app.adapters.stt.base import FakeSTT, set_stt_override
from app.db import session_factory
from app.models import GeneratedMessage, Job, Message, ScheduledAction, VoiceTranscription
from tests.conftest import H, run_all_jobs
from tests.integration.test_voice import audio, finish, upload


@pytest.fixture
def voice(client):
    set_stt_override(FakeSTT())
    return client


def test_voice_endpoints_require_login_and_csrf(voice):
    from app.main import app
    anon = TestClient(app)
    vid = upload(voice).json()["id"]
    for method, path in [("get", "/voice/status"), ("get", "/voice/transcriptions"), ("get", f"/voice/transcriptions/{vid}"),
                         ("delete", f"/voice/transcriptions/{vid}"), ("delete", "/voice/transcriptions")]:
        assert getattr(anon, method)(f"/api/v1{path}", headers=H).status_code == 401, (method, path)
    r = anon.post("/api/v1/voice/transcriptions", files={"file": ("a.webm", audio(), "audio/webm")}, headers=H)
    assert r.status_code == 401                                                       # no public transcription endpoint
    assert voice.post("/api/v1/voice/transcriptions", files={"file": ("a.webm", audio(), "audio/webm")}).json()["error"]["code"] == "csrf"
    assert voice.delete("/api/v1/voice/transcriptions").status_code == 403


def test_raw_audio_is_not_retained_after_processing_in_any_outcome(voice):
    finish(voice, audio("a normal note"))
    finish(voice, audio(b"FAKE_FAIL"))
    finish(voice, audio(b"FAKE_EMPTY"))
    cancelled = upload(voice).json()["id"]
    voice.delete(f"/api/v1/voice/transcriptions/{cancelled}", headers=H)
    run_all_jobs()
    with session_factory()() as s:
        assert s.scalar(select(func.count()).select_from(VoiceTranscription)) == 4
        assert s.scalar(select(func.count()).select_from(VoiceTranscription).where(VoiceTranscription.audio.is_not(None))) == 0


def test_api_responses_never_contain_audio_or_secrets(voice):
    out = finish(voice, audio("a normal note"))
    assert not ({"audio", "audio_bytes", "user_id", "workspace_id"} & set(out))
    assert "audio" not in str(voice.get("/api/v1/voice/transcriptions").json())


def test_audio_and_transcripts_are_never_written_to_logs(voice, caplog):
    secret_text, secret_email = "zebra-unicorn-4417", "leak.test@example.com"
    caplog.set_level(logging.DEBUG)
    set_llm_override(FakeLLM(lambda s, u: {"text": f"{secret_text} {secret_email}."}))
    finish(voice, audio(f"{secret_text} {secret_email}"), cleanup=True)           # success + cleanup path
    finish(voice, audio(f"{secret_text}"), cleanup=True)

    class Boom(FakeSTT):
        def transcribe(self, *a, **k):
            raise RuntimeError(f"provider echoed {secret_text} {secret_email}")
    set_stt_override(Boom())
    finish(voice, audio(f"{secret_text}"))                                            # crash path
    logged = "\n".join(r.getMessage() for r in caplog.records) + caplog.text
    assert "voice" in logged                                                           # we do log something (ids, sizes, timing)...
    assert secret_text not in logged and secret_email not in logged and "FAKE:" not in logged   # ...but never content
    with session_factory()() as s:                                                     # the audit trail is content-free too
        from app.models import AuditLog
        assert secret_text not in str([a.data for a in s.scalars(select(AuditLog))])


def test_dictation_never_sends_schedules_or_drafts_anything(voice):
    set_llm_override(FakeLLM(lambda s, u: {"text": "Please send the proposal today."}))
    finish(voice, audio("please send the proposal today"), cleanup=True)
    finish(voice, audio("send an email to everyone right now"), language="en")
    voice.delete("/api/v1/voice/transcriptions", headers=H)
    with session_factory()() as s:
        for model in (Message, ScheduledAction, GeneratedMessage):
            assert s.scalar(select(func.count()).select_from(model)) == 0, model.__name__
        assert {j.type for j in s.scalars(select(Job))} == {"voice_transcribe"}        # the only work it ever queues
    assert MockAdapter.outbox == []


@pytest.mark.parametrize("raw,tampered", [
    ("pay 5000 rupees by friday", "Pay 50000 rupees by Friday."),
    ("pay 5000 rupees by friday", "Pay 5000 rupees by Monday."),
    ("see https://flowhq.in/pricing today", "See https://flowhq.in/plans today."),
    ("write to asha@brightsmile.in please", "Write to asha@brightsmile.com please."),
    ("call 98765 43210 tomorrow", "Call 98765 43211 tomorrow."),
    ("it is a 20% discount for Rohan", "It is a 25% discount for Rohan."),
    ("it is a 20% discount for Rohan", "It is a 20% discount for Rahul."),
    ("kal 3 baje call karna hai", "Kal 4 baje call karna hai."),
])
def test_ai_cleanup_cannot_silently_change_numbers_links_or_names(voice, raw, tampered):
    set_llm_override(FakeLLM(lambda s, u: {"text": tampered}))
    out = finish(voice, audio(raw), cleanup=True)
    assert out["text"] == raw and out["cleaned"] is False and "not applied" in out["note"]
    with session_factory()() as s:
        assert s.scalars(select(VoiceTranscription)).one().clean_text is None            # the tampered text was not even stored


def test_the_transcript_not_the_cleanup_is_the_source_of_truth(voice):
    set_llm_override(FakeLLM(lambda s, u: {"text": "Totally different content."}))
    out = finish(voice, audio("call Rohan at 5 pm"), cleanup=True)
    assert out["raw_text"] == "call Rohan at 5 pm" and out["text"] == out["raw_text"]


def test_one_users_dictation_history_is_not_readable_by_another_workspace(voice):
    from tests.conftest import login, make_user
    vid = finish(voice, audio("workspace one secret"))["id"]
    make_user("intruder@example.com", ws_name="Other workspace")
    other = login("intruder@example.com")
    set_stt_override(FakeSTT())
    assert other.get(f"/api/v1/voice/transcriptions/{vid}").status_code == 404
    assert "workspace one secret" not in str(other.get("/api/v1/voice/transcriptions").json())
