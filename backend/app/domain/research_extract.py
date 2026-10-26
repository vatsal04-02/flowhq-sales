"""Turn extracted page structure into evidence findings. Every excerpt is copied verbatim from the page,
so a quote check against it is meaningful."""
import re

SERVICE_PATH = re.compile(r"/(about|services?|solutions?|products?|what-we-do|treatments?|capabilities|industries|offerings?)(/|$|\.)", re.I)
GENERIC_HEADINGS = {"home", "contact", "contact us", "about us", "about", "menu", "services", "our services",
                    "welcome", "blog", "faq", "testimonials", "reviews", "get in touch", "follow us", "footer",
                    "privacy policy", "terms", "our team", "latest news"}


def _clean(s: str, n: int = 300) -> str:
    return " ".join(s.split())[:n]


def build_findings(pages: list[dict]) -> list[dict]:
    """pages: [{url, title, meta, headings[(tag,text)], text}] -> findings with kind/confidence/excerpt."""
    out: list[dict] = []
    seen: set[str] = set()

    def add(url, finding, excerpt, confidence, topic):
        key = excerpt.lower()
        excerpt = _clean(excerpt)
        if len(excerpt) < 6 or key in seen:
            return
        seen.add(key)
        out.append({"url": url, "finding": finding, "excerpt": excerpt, "kind": "verified",
                    "confidence": confidence, "topic": topic})

    for i, p in enumerate(pages):
        url = p["url"]
        if i == 0:
            if p.get("meta"):
                add(url, "Describes itself as", p["meta"], "high", "describes")
            h1 = next((t for tag, t in p.get("headings", []) if tag == "h1"), None)
            if h1 and h1.lower() not in GENERIC_HEADINGS:
                add(url, "Headline on its homepage", h1, "high", "headline")
            elif p.get("title"):
                add(url, "Site title", p["title"], "medium", "title")
        n = 0
        for tag, t in p.get("headings", []):
            if tag in ("h2", "h3") and t.lower() not in GENERIC_HEADINGS and 4 <= len(t) <= 80 and n < 3:
                add(url, "Lists an offering or section", t, "medium", "offering")
                n += 1
    texts = " ".join(p.get("text", "") for p in pages)[:1500]
    if texts and pages:
        out.append({"url": pages[0]["url"], "finding": "Homepage text sample", "excerpt": _clean(texts, 1500),
                    "kind": "verified", "confidence": "low", "topic": "sample"})
    return out[:10]
