"""Explicit lead status transition rules. AI code must never write status directly."""

LEAD_STATUSES = [
    "imported", "needs_research", "qualified", "unqualified", "ready_for_review",
    "approved", "active_outreach", "replied", "interested", "meeting_booked",
    "converted", "not_interested", "bounced", "unsubscribed", "suppressed",
]

# Terminal-ish states a person (or the system on opt-out) can reach from nearly anywhere.
_STOP = {"unsubscribed", "suppressed", "bounced"}
_OUTREACH = {"approved", "active_outreach", "replied", "interested", "meeting_booked",
             "converted", "not_interested"}

TRANSITIONS: dict[str, set[str]] = {
    "imported": {"needs_research", "unqualified"} | _STOP,
    "needs_research": {"qualified", "unqualified", "ready_for_review"} | _STOP,
    "qualified": {"ready_for_review", "unqualified", "needs_research"} | _STOP,
    "unqualified": {"needs_research", "qualified"} | _STOP,
    "ready_for_review": {"approved", "unqualified", "needs_research"} | _STOP,
    "approved": {"active_outreach", "ready_for_review"} | _STOP,
    "active_outreach": {"replied", "approved", "not_interested"} | _STOP,
    "replied": {"interested", "not_interested", "meeting_booked", "active_outreach"} | _STOP,
    "interested": {"meeting_booked", "not_interested", "converted"} | _STOP,
    "meeting_booked": {"converted", "not_interested", "interested"} | _STOP,
    "converted": set(),
    "not_interested": {"needs_research"} | _STOP,
    "bounced": set(),
    "unsubscribed": set(),  # only an explicit, audited un-suppress workflow may revisit
    "suppressed": set(),
}

# Statuses an operator may set by hand through the API (no outreach-state shortcuts).
MANUAL_TARGETS = {"needs_research", "qualified", "unqualified", "not_interested",
                  "unsubscribed", "suppressed"}


class IllegalTransition(ValueError):
    pass


def can_transition(old: str, new: str) -> bool:
    return new in TRANSITIONS.get(old, set())


def check_transition(old: str, new: str) -> None:
    if old == new:
        return
    if not can_transition(old, new):
        raise IllegalTransition(f"{old} -> {new} is not allowed")


def is_contactable_status(status: str) -> bool:
    return status not in {"unsubscribed", "suppressed", "bounced", "not_interested", "converted"}
