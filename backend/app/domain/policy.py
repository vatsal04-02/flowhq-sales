"""Pure send-policy gate. Called immediately before every send; there is no other path to send."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

STOP_STATUSES = {"unsubscribed", "suppressed", "bounced", "not_interested", "converted", "replied",
                 "interested", "meeting_booked"}


@dataclass
class GateInput:
    now: datetime
    kill_switch: bool
    campaign_status: str
    campaign_lead_state: str
    lead_status: str
    lead_opted_out: bool
    lead_region: str | None
    blocked_regions: list[str]
    suppressed_reason: str | None
    has_address: bool
    recipient: str | None
    msg_status: str
    msg_hash: str
    msg_approved_hash: str | None
    channel_can_send: bool
    account_active: bool
    sent_today_account: int
    account_daily_limit: int
    sent_today_campaign: int
    campaign_daily_limit: int
    timezone: str
    work_start: int
    work_end: int
    replied: bool


@dataclass
class Decision:
    action: str  # allow | defer | block
    reason: str = ""
    until: datetime | None = None
    hold: bool = False  # block that is fixable by the operator (resume campaign, add address): keep action queued


def next_window(now: datetime, tz: str, start: int, end: int) -> datetime | None:
    """None if `now` is inside working hours (Mon-Fri), else the next opening time (UTC-aware)."""
    z = ZoneInfo(tz)
    local = now.astimezone(z)
    if local.weekday() < 5 and start <= local.hour < end:
        return None
    day = local.date()
    if local.weekday() < 5 and local.hour < start:
        pass
    else:
        day = day + timedelta(days=1)
    while datetime.combine(day, time(), z).weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, time(start), z).astimezone(now.tzinfo)


def check(g: GateInput) -> Decision:
    def block(r: str, hold: bool = False) -> Decision:
        return Decision("block", r, hold=hold)
    if g.kill_switch:
        return block("global kill switch is on", hold=True)
    if not g.channel_can_send:
        return block("channel cannot send (manual action required)")
    if not g.account_active:
        return block("channel account is not active", hold=True)
    if g.msg_status != "approved" or not g.msg_approved_hash or g.msg_approved_hash != g.msg_hash:
        return block("message is not approved (or was edited after approval)", hold=True)  # re-approving resumes it
    if g.campaign_status != "active":
        return block(f"campaign is {g.campaign_status}", hold=g.campaign_status in ("paused", "draft"))
    if g.campaign_lead_state in ("stopped", "completed"):
        return block(f"sequence {g.campaign_lead_state}")
    if g.lead_opted_out or g.suppressed_reason:
        return block(f"lead suppressed ({g.suppressed_reason or 'opted out'})")
    if g.lead_status in STOP_STATUSES or g.replied:
        return block(f"lead status {g.lead_status}" if g.lead_status in STOP_STATUSES else "lead already replied")
    if g.lead_region and g.lead_region.upper() in [r.upper() for r in g.blocked_regions]:
        return block(f"region {g.lead_region} is blocked for this campaign")
    if not g.recipient:
        return block("lead has no address for this channel")
    if not g.has_address:
        return block("campaign has no physical postal address (required in footer)", hold=True)
    if g.sent_today_account >= g.account_daily_limit or g.sent_today_campaign >= g.campaign_daily_limit:
        tomorrow = (g.now.astimezone(ZoneInfo(g.timezone)) + timedelta(days=1)).replace(hour=g.work_start, minute=0, second=0, microsecond=0)
        return Decision("defer", "daily sending limit reached", tomorrow.astimezone(g.now.tzinfo))
    nxt = next_window(g.now, g.timezone, g.work_start, g.work_end)
    if nxt:
        return Decision("defer", "outside working hours", nxt)
    return Decision("allow")
