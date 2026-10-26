"""Benchmark the configured speech-to-text provider on YOUR recordings, especially Hindi and Hinglish.

    STT_PROVIDER=openai_compat STT_BASE_URL=http://localhost:8001/v1 STT_MODEL=Systran/faster-whisper-small \\
        python -m scripts.bench_stt path/to/samples [--max-wer 0.35]

`path/to/samples/manifest.json` lists your recordings and what was actually said (see scripts/stt_samples.example.json for a
ready-made reading script; record each line, save as wav/webm/m4a):

    [{"file": "hinglish_01.wav", "language": "hinglish", "expected": "kal teen baje Rohan ko phone karna hai"}, ...]

Per sample and per language it reports: word error rate, how many critical details (numbers, links, emails, month/day words)
came back intact, whether the requested script came back (Hinglish must be Roman letters, Hindi must be Devanagari), and latency.
Use it to pick the smallest model that is good enough for your accent and vocabulary. Nothing here is a pass/fail claim about a
model: quality depends on the model size, your microphone and your accent, so measure rather than assume.
"""
import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

from app.adapters.stt.base import STTError, get_stt
from app.domain import voice as dv


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text).lower()
    return re.findall(r"[\w'’]+", text)


def wer(expected: str, actual: str) -> float:
    """Word error rate: word-level edit distance / number of expected words (0 = perfect, can exceed 1)."""
    ref, hyp = words(expected), words(actual)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / len(ref)


def detail_recall(expected: str, actual: str) -> float | None:
    """Share of the expected numbers, links, emails and date words that appear in the transcript (None if there were none)."""
    want = dv.protected_tokens(expected)
    total = sum(want.values())
    if not total:
        return None
    return sum((want & dv.protected_tokens(actual)).values()) / total


def script_ok(language: str, actual: str) -> bool | None:
    if language == "hinglish":
        return not dv.has_devanagari(actual)
    if language == "hi":
        return dv.has_devanagari(actual)
    return None


MIME = {".wav": "audio/wav", ".webm": "audio/webm", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".flac": "audio/flac"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("samples", type=Path)
    ap.add_argument("--max-wer", type=float, default=None, help="exit non-zero if any language's mean WER is above this")
    args = ap.parse_args()
    stt = get_stt()
    if stt is None:
        raise SystemExit("Set STT_PROVIDER=openai_compat (and STT_BASE_URL / STT_MODEL) first.")
    manifest = json.loads((args.samples / "manifest.json").read_text(encoding="utf-8"))
    rows: dict[str, list[dict]] = defaultdict(list)
    print(f"provider={stt.name} processing={stt.processing} samples={len(manifest)}\n")
    for item in manifest:
        path = args.samples / item["file"]
        lang = item.get("language", "auto")
        kind = dv.sniff_audio(path.read_bytes()[:16])
        mime, ext = (kind.mime, kind.ext) if kind else (MIME.get(path.suffix.lower(), "audio/wav"), path.suffix.lstrip(".") or "wav")
        code, prompt = dv.stt_options(lang)
        t0 = time.perf_counter()
        try:
            text = dv.normalize_transcript(stt.transcribe(path.read_bytes(), mime=mime, ext=ext, language=code, prompt=prompt))
        except STTError as exc:
            print(f"  {item['file']:<28} {lang:<9} FAILED: {exc.code}")
            rows[lang].append({"wer": 1.0, "recall": None, "script": None, "lat": time.perf_counter() - t0})
            continue
        r = {"wer": wer(item["expected"], text), "recall": detail_recall(item["expected"], text), "script": script_ok(lang, text), "lat": time.perf_counter() - t0}
        rows[lang].append(r)
        rec = "-" if r["recall"] is None else f"{r['recall']:.0%}"
        scr = "-" if r["script"] is None else ("ok" if r["script"] else "WRONG")
        print(f"  {item['file']:<28} {lang:<9} WER {r['wer']:.2f}  details {rec:>4}  script {scr:<5} {r['lat']:.1f}s")
        if r["wer"] > 0.3:
            print(f"      expected: {item['expected']}\n      heard:    {text}")
    print("\nBy language:")
    worst = 0.0
    for lang, rs in sorted(rows.items()):
        mean = statistics.mean(r["wer"] for r in rs); worst = max(worst, mean)
        rec = [r["recall"] for r in rs if r["recall"] is not None]; scr = [r["script"] for r in rs if r["script"] is not None]
        print(f"  {lang:<9} n={len(rs):<3} mean WER {mean:.2f}"
              + (f"  details kept {statistics.mean(rec):.0%}" if rec else "")
              + (f"  right script {sum(scr)}/{len(scr)}" if scr else "")
              + f"  median latency {statistics.median(r['lat'] for r in rs):.1f}s")
    if args.max_wer is not None and worst > args.max_wer:
        print(f"\nFAIL: worst mean WER {worst:.2f} exceeds --max-wer {args.max_wer}")
        sys.exit(1)


if __name__ == "__main__":
    main()
