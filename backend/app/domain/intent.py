"""Rule-based reply intent classifier: a safe, instant baseline. Opt-outs are ALWAYS decided here,
never left to a model. Anything uncertain is 'unclear' and goes to a human."""
import re

RULES: list[tuple[str, str, int]] = [
    ("unsubscribe", r"\b(unsubscribe|remove me|stop (emailing|contacting|messaging)|do not (contact|email)|don'?t (contact|email)|take me off|opt[- ]?out)\b", 95),
    ("out_of_office", r"\b(out of (the )?office|on (annual )?leave|automatic reply|auto[- ]?reply|away until)\b", 90),
    ("wrong_person", r"\b(wrong person|not the right person|no longer (work|with)|left the company|try (contacting|reaching))\b", 80),
    ("meeting_request", r"\b(book|schedule|set up|arrange)\b.*\b(call|meeting|demo|chat)\b|\b(free (on|at|tomorrow|next)|let'?s (talk|chat|connect|meet)|send (me )?(a )?(calendar|invite)|calendly)\b", 80),
    ("not_interested", r"\b(not interested|no thanks|no thank you|not a (good )?fit|we('re| are) (all set|good)|pass on this|not (looking|needed))\b", 85),
    ("requesting_info", r"\b(more (info|information|details)|pricing|how much|cost|case stud|tell me more|send (me )?(details|info)|what (does|do) (it|this|you))\b", 75),
    ("interested", r"\b(interested|sounds (good|great|interesting)|yes,? please|love to|would like to|keen|let me know more)\b", 75),
    ("objection", r"\b(too expensive|already (have|use|work)|budget|not now|maybe later|busy|next quarter)\b", 65),
]
POSITIVE = {"interested", "meeting_request", "requesting_info"}
STOPPING = {"unsubscribe", "not_interested", "wrong_person", "interested", "meeting_request", "requesting_info",
            "objection", "unclear"}  # out_of_office pauses nothing: sequence continues later


def classify(text: str) -> tuple[str, int]:
    t = re.split(r"\n\s*>|\n\s*on .{5,80} wrote:|\n-{2,}\s*original message", text.lower(), maxsplit=1)[0]  # ignore quoted history
    t = re.sub(r"\s+", " ", t)
    for intent, pat, conf in RULES:
        if re.search(pat, t, re.S):
            return intent, conf
    return "unclear", 30


SUGGESTED = {
    "interested": "Great to hear! Would a 15-minute call this week work? Here are a couple of times: [add times].",
    "requesting_info": "Happy to share more. In short: [add 2-3 lines about the offer]. Would a quick call help?",
    "meeting_request": "Thanks! [Add your calendar link or 2-3 time options].",
    "objection": "Understood, thanks for the honest reply. Would it be useful if I checked back in [timeframe]?",
    "not_interested": "No problem at all, thanks for letting me know. I won't follow up again.",
    "wrong_person": "Thanks for letting me know. Is there someone else who looks after this?",
    "out_of_office": "",
    "unsubscribe": "",
    "unclear": "Thanks for your reply. Could you tell me a bit more about what would be most useful?",
}
