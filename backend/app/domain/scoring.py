"""Deterministic ICP scoring. Unknown attributes are neither matches nor failures: they are left out
of the score and lower the *confidence* instead."""
from dataclasses import asdict, dataclass, field

DEFAULT_WEIGHTS = {"industry": 30, "region": 20, "keywords": 40, "evidence": 10}
DEFAULT_THRESHOLDS = {"strong": 80, "possible": 60, "weak": 40, "min_confidence": 40}


@dataclass
class Facts:
    industry: str | None = None
    region: str | None = None
    text: str = ""  # lowercased evidence + company description
    evidence_count: int = 0


@dataclass
class Criterion:
    key: str
    label: str
    weight: int
    result: str  # match | no_match | unknown
    points: float = 0.0
    detail: str = ""


@dataclass
class ScoreResult:
    score: int | None
    confidence: int
    klass: str  # strong | possible | weak | unqualified | insufficient
    criteria: list[Criterion] = field(default_factory=list)
    excluded_by: str | None = None

    def breakdown(self) -> list[dict]:
        return [asdict(c) for c in self.criteria]


def _terms(v) -> list[str]:
    return [t.strip().lower() for t in (v or []) if t and t.strip()]


def evaluate(icp: dict, facts: Facts, thresholds: dict | None = None) -> ScoreResult:
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    w = {**DEFAULT_WEIGHTS, **(icp.get("weights") or {})}
    text = (facts.text or "").lower()
    industry = (facts.industry or "").lower()
    crit: list[Criterion] = []

    for term in _terms(icp.get("exclude_keywords")):
        if term in text or term in industry:
            return ScoreResult(0, 100, "unqualified",
                               [Criterion("exclusion", "Exclusion criteria", 0, "match", 0, f"matched '{term}'")],
                               excluded_by=term)

    industries = _terms(icp.get("industries"))
    if industries:
        hay = f"{industry} {text}"
        if not hay.strip():
            crit.append(Criterion("industry", "Target industry", w["industry"], "unknown", 0, "no industry info"))
        elif any(i in hay for i in industries):
            crit.append(Criterion("industry", "Target industry", w["industry"], "match", w["industry"], "industry term found"))
        else:
            crit.append(Criterion("industry", "Target industry", w["industry"], "no_match", 0, "no target industry term found"))

    regions = [r.upper() for r in _terms(icp.get("regions"))]
    if regions:
        if not facts.region:
            crit.append(Criterion("region", "Geography", w["region"], "unknown", 0, "lead region not provided"))
        elif facts.region.upper() in regions:
            crit.append(Criterion("region", "Geography", w["region"], "match", w["region"], facts.region.upper()))
        else:
            crit.append(Criterion("region", "Geography", w["region"], "no_match", 0, facts.region.upper()))

    keywords = _terms(icp.get("keywords"))
    if keywords:
        if not text.strip():
            crit.append(Criterion("keywords", "Services / pain-point keywords", w["keywords"], "unknown", 0, "no evidence text"))
        else:
            found = [k for k in keywords if k in text]
            frac = min(1.0, len(found) / min(len(keywords), 2))
            crit.append(Criterion("keywords", "Services / pain-point keywords", w["keywords"],
                                  "match" if found else "no_match", round(w["keywords"] * frac, 1),
                                  f"found: {', '.join(found)}" if found else "none found"))

    min_ev = int(icp.get("min_evidence", 2))
    ok = facts.evidence_count >= min_ev
    crit.append(Criterion("evidence", "Evidence quality", w["evidence"], "match" if ok else "no_match",
                          w["evidence"] if ok else 0, f"{facts.evidence_count} evidence items (min {min_ev})"))

    total_w = sum(c.weight for c in crit) or 1
    known = [c for c in crit if c.result != "unknown"]
    known_w = sum(c.weight for c in known)
    confidence = round(100 * known_w / total_w)
    # a lead with no research evidence can never be "confidently" scored
    if known_w == 0 or confidence < th["min_confidence"] or facts.evidence_count == 0:
        return ScoreResult(None, confidence, "insufficient", crit)
    score = round(100 * sum(c.points for c in known) / known_w)
    klass = ("strong" if score >= th["strong"] else "possible" if score >= th["possible"]
             else "weak" if score >= th["weak"] else "unqualified")
    return ScoreResult(score, confidence, klass, crit)
