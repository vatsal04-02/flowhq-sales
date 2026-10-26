"""Benchmark a local model (Ollama) for FlowHQ's personalization task.

    LLM_PROVIDER=ollama LLM_MODEL=qwen2.5:1.5b-instruct python -m scripts.bench_llm [runs]

Reports per model: valid-JSON rate, evidence-verified-claim rate, fabricated-claim rate, and latency.
Pick the smallest model whose fabricated-claim rate is 0 and whose latency you can live with. Because every
claim is verified against stored evidence and drafts need approval, a model that fails here degrades to templates;
it can never push a made-up fact into a sent email.
"""
import statistics
import sys
import time

from app.adapters.llm.base import LLMUnavailable, get_llm
from app.domain import message_validator as mv
from app.services.personalize import SYSTEM, Slots

SAMPLES = [
    ["Family dental clinic offering implants and orthodontics in Pune", "Modern dental care for families", "Teeth whitening"],
    ["We build custom CNC machined parts for aerospace", "ISO 9001 certified workshop in Pune", "Rapid prototyping"],
    ["Boutique law firm focused on startup fundraising", "Our partners advise founders on SAFEs and term sheets"],
    ["Coworking space and meeting rooms in Bandra", "Day passes and private offices"],
]


def main(runs: int = 1) -> None:
    llm = get_llm()
    if llm is None:
        raise SystemExit("Set LLM_PROVIDER=ollama (and LLM_MODEL) first.")
    ok = verified = fabricated = total_claims = 0
    lat: list[float] = []
    n = 0
    for _ in range(runs):
        for texts in SAMPLES:
            n += 1
            ev = {f"e{i + 1}": {"kind": "verified", "excerpt": t, "url": "bench"} for i, t in enumerate(texts)}
            user = ("Company: Example\nRecipient role: Owner\nTone: friendly\nOffer: We automate appointment reminders.\nEvidence (each line is 'id: text'):\n<untrusted>\n"
                    + "\n".join(f"{k}: {v['excerpt']}" for k, v in ev.items()) + "\n</untrusted>")
            t0 = time.perf_counter()
            try:
                out, _ = llm.complete_json(system=SYSTEM, user=user, schema=Slots, max_tokens=250)
            except LLMUnavailable as exc:
                print("  failed:", str(exc)[:100]); continue
            lat.append(time.perf_counter() - t0)
            ok += 1
            good, bad = mv.verify_claims([c.model_dump() for c in out.claims], ev)
            verified += len(good); fabricated += len(bad); total_claims += len(out.claims)
    print(f"model={llm.name} samples={n}")
    print(f"valid JSON: {ok}/{n}")
    print(f"claims verified: {verified}/{total_claims}  fabricated/unsupported: {fabricated}")
    if lat:
        print(f"latency s: median={statistics.median(lat):.1f} max={max(lat):.1f}  (per draft; research is model-free)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
