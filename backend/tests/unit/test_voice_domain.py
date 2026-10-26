import pytest

from app.adapters.stt.base import infer_processing
from app.domain import voice as v

# ---------- audio sniffing ----------

HEADERS = {
    "webm": (b"\x1a\x45\xdf\xa3" + b"\x00" * 20, "audio/webm"),
    "ogg": (b"OggS\x00\x02" + b"\x00" * 20, "audio/ogg"),
    "wav": (b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 20, "audio/wav"),
    "m4a": (b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 20, "audio/mp4"),
    "mp3-id3": (b"ID3\x03\x00" + b"\x00" * 20, "audio/mpeg"),
    "mp3-frame": (b"\xff\xfb\x90\x00" + b"\x00" * 20, "audio/mpeg"),
    "flac": (b"fLaC" + b"\x00" * 20, "audio/flac"),
}


@pytest.mark.parametrize("name", HEADERS)
def test_sniffs_known_audio_containers(name):
    data, mime = HEADERS[name]
    assert v.sniff_audio(data).mime == mime


@pytest.mark.parametrize("data", [b"", b"<html><script>alert(1)</script>", b"%PDF-1.7", b"MZ\x90\x00", b"GIF89a", b"\x00" * 64, b"just text " * 10])
def test_rejects_things_that_are_not_audio(data):
    assert v.sniff_audio(data) is None


# ---------- languages ----------

def test_language_options_for_each_supported_language():
    assert v.stt_options("en")[0] == "en"
    assert v.stt_options("auto")[0] is None
    code, prompt = v.stt_options("hi")
    assert code == "hi" and v.has_devanagari(prompt)


def test_hinglish_asks_for_hindi_speech_in_roman_letters():
    code, prompt = v.stt_options("hinglish")
    assert code == "hi" and not v.has_devanagari(prompt) and prompt.isascii()


def test_hinglish_returning_devanagari_is_flagged_not_silently_accepted():
    assert v.script_note("hinglish", "मैं कल आऊँगा") is not None
    assert v.script_note("hinglish", "main kal aaunga") is None
    assert v.script_note("hi", "मैं कल आऊँगा") is None


def test_normalize_transcript_collapses_whitespace_and_strips_control_characters():
    assert v.normalize_transcript("  hello   world\x00\x07 \n\n  next\tline ") == "hello world\nnext line"
    assert len(v.normalize_transcript("a" * 9000)) == 5000


# ---------- cleanup guard: what a cleanup is allowed to do ----------

RAW = "um so the price is 5,000 rupees uh and our site is www.flowhq.in please email rohan@brightsmile.in about it on March 3"


def test_accepts_a_light_edit_that_keeps_every_fact():
    ok = "So the price is 5,000 rupees and our site is www.flowhq.in. Please email rohan@brightsmile.in about it on March 3."
    assert v.check_cleanup(RAW, ok).ok


@pytest.mark.parametrize("bad,reason", [
    ("So the price is 6,000 rupees and our site is www.flowhq.in. Please email rohan@brightsmile.in about it on March 3.", "changed_facts"),
    ("So the price is 5,000 rupees and our site is www.flowhq.com. Please email rohan@brightsmile.in about it on March 3.", "changed_facts"),
    ("So the price is 5,000 rupees and our site is www.flowhq.in. Please email rohan@brightsmile.com about it on March 3.", "changed_facts"),
    ("So the price is 5,000 rupees and our site is www.flowhq.in. Please email rohan@brightsmile.in about it on March 4.", "changed_facts"),
    ("So the price is 5,000 rupees and our site is www.flowhq.in. Please email rohan@brightsmile.in about it on May 3.", "changed_facts"),
    ("So the price is 5,000 rupees and our site is www.flowhq.in. Please email rohan@brightsmile.in about it.", "changed_facts"),
    ("So the price is 5,000 rupees and 20% off, our site is www.flowhq.in. Please email rohan@brightsmile.in on March 3.", "changed_facts"),
    ("", "empty"),
    ("ok", "length"),
])
def test_rejects_a_cleanup_that_changes_critical_details(bad, reason):
    verdict = v.check_cleanup(RAW, bad)
    assert not verdict.ok and verdict.reason == reason


def test_equivalent_number_formatting_is_not_a_change():
    assert v.check_cleanup("it costs 1,000 rupees total", "It costs 1000 rupees total.").ok
    assert v.check_cleanup("call me at 98765 43210 today", "Call me at 98765 43210 today.").ok
    assert not v.check_cleanup("call me at 98765 43210 today", "Call me at 9876543210 today.").ok  # reformatting a phone number is still a change


def test_devanagari_digits_count_as_the_same_number():
    assert v.protected_tokens("कीमत ५०० रुपये है") == v.protected_tokens("कीमत 500 रुपये है")


def test_a_changed_name_is_rejected():
    raw = "tell Rohan that Priya from Pune will call"
    assert v.check_cleanup(raw, "Tell Rohan that Priya from Pune will call.").ok
    assert v.check_cleanup(raw, "Tell Rahul that Priya from Pune will call.").reason == "changed_names"


def test_a_cleanup_that_rewrites_the_message_is_rejected():
    raw = "we should send them a short follow up about the dental implant offer next week"
    rewritten = "Dear valued customer, we are thrilled to present our exclusive premium dental offering with outstanding savings."
    assert v.check_cleanup(raw, rewritten).reason in ("rewrote_too_much", "length")


def test_a_cleanup_cannot_invent_content():
    raw = "send the proposal on monday"
    assert not v.check_cleanup(raw, "Send the proposal on Monday and offer them a 50% discount plus a free consultation call.").ok


def test_hinglish_light_edit_is_accepted_but_transliteration_is_not():
    raw = "haan toh price 5000 rupaye hai aur Rohan ko kal follow up email bhejna hai"
    assert v.check_cleanup(raw, "Haan, toh price 5000 rupaye hai aur Rohan ko kal follow-up email bhejna hai.").ok
    assert not v.check_cleanup(raw, "हाँ तो प्राइस 5000 रुपये है और Rohan को कल फ़ॉलो-अप ईमेल भेजना है").ok  # same script and language must be kept


def test_hindi_text_in_devanagari_round_trips():
    raw = "कल दोपहर 3 बजे रोहन को फोन करना है"
    assert v.check_cleanup(raw, "कल दोपहर 3 बजे रोहन को फोन करना है।").ok
    assert not v.check_cleanup(raw, "कल दोपहर 4 बजे रोहन को फोन करना है।").ok


def test_prompt_tells_the_model_the_transcript_is_data():
    assert "<transcript>" in v.CLEANUP_SYSTEM and "ignore" in v.CLEANUP_SYSTEM.lower()


# ---------- where is processing done ----------

@pytest.mark.parametrize("url,expected", [
    ("http://localhost:8001/v1", "local"), ("http://127.0.0.1:9000/v1", "local"), ("http://host.docker.internal:8001/v1", "local"),
    ("http://whisper:8000/v1", "local"), ("http://192.168.1.20:8000/v1", "local"), ("http://10.0.0.5/v1", "local"),
    ("https://api.openai.com/v1", "cloud"), ("https://stt.example.com/v1", "cloud"), ("http://8.8.8.8/v1", "cloud"),
])
def test_infers_local_versus_cloud_from_the_endpoint(url, expected):
    assert infer_processing(url) == expected


def test_explicit_override_wins():
    assert infer_processing("http://localhost:8001/v1", "cloud") == "cloud"
    assert infer_processing("https://stt.example.com/v1", "local") == "local"
