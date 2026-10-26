import json
from pathlib import Path

import pytest

from scripts.bench_stt import detail_recall, script_ok, wer


def test_wer_counts_word_level_errors():
    assert wer("call rohan at five", "call rohan at five") == 0
    assert wer("call rohan at five", "call rohan at six") == 0.25
    assert wer("call rohan", "call rohan at five") == 1.0           # insertions count, so WER can exceed the error share of the output
    assert wer("", "") == 0 and wer("", "x") == 1
    assert wer("Kal 3 baje, Rohan!", "kal 3 baje rohan") == 0        # case and punctuation do not count


def test_detail_recall_checks_numbers_links_and_emails():
    exp = "price 5000 rupaye, mail asha@brightsmile.in or see flowhq.in"
    assert detail_recall(exp, exp) == 1
    assert detail_recall(exp, "price 6000 rupaye, mail asha@brightsmile.in or see flowhq.in") == pytest.approx(2 / 3)  # three critical details (price, email, link); one came back wrong
    assert detail_recall("no details here", "anything") is None


def test_script_expectations_per_language():
    assert script_ok("hinglish", "kal teen baje") is True and script_ok("hinglish", "कल तीन बजे") is False
    assert script_ok("hi", "कल तीन बजे") is True and script_ok("hi", "kal teen baje") is False
    assert script_ok("en", "anything") is None


def test_example_manifest_is_well_formed_and_covers_all_three_languages():
    items = json.loads((Path(__file__).parents[2] / "scripts" / "stt_samples.example.json").read_text(encoding="utf-8"))
    assert {i["language"] for i in items} == {"en", "hi", "hinglish"}
    assert all({"file", "language", "expected"} <= set(i) for i in items)
