export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Requested-With", "flowhq"); // CSRF guard expected by the API for mutations
  let body = init.body;
  if (init.json !== undefined) { headers.set("Content-Type", "application/json"); body = JSON.stringify(init.json); }
  const res = await fetch(`/api/v1${path}`, { ...init, headers, body, credentials: "same-origin" });
  if (res.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
    location.href = "/login";
  }
  if (!res.ok) {
    let code = "error", msg = res.statusText;
    try { const e = (await res.json()).error; code = e.code; msg = e.message; } catch { /* non-JSON error */ }
    throw new ApiError(res.status, code, msg);
  }
  return res.json() as Promise<T>;
}

export type Lead = {
  id: string; first_name: string | null; last_name: string | null; title: string | null;
  email: string | null; email_norm: string | null; phone_e164: string | null; region: string | null;
  linkedin_url: string | null; instagram_url: string | null; status: string; opted_out: boolean;
  possible_duplicate_of: string | null; custom: Record<string, unknown>; created_at: string;
  research_status: string; icp_score: number | null; icp_class: string | null; icp_confidence: number | null;
};
export type LeadDetail = Lead & {
  raw: Record<string, string>; lawful_basis: string | null;
  company: { name: string | null; domain: string | null; website: string | null } | null;
  timeline: { kind: string; at: string; data: Record<string, unknown> }[];
  evidence: Evidence[]; icp_breakdown: Criterion[];
};
export type Evidence = { id: string; finding: string; excerpt: string; url: string; kind: string; confidence: string; retrieved_at?: string };
export type Criterion = { key: string; label: string; weight: number; result: string; points: number; detail: string };
export type Batch = {
  id: string; filename: string; status: string; headers: string[]; mapping: Record<string, string>;
  total_rows: number; next_row: number; created_count: number; duplicate_count: number;
  invalid_count: number; suppressed_count: number; error: string | null;
};
export type Job = {
  id: string; type: string; state: string; attempts: number; max_attempts: number;
  last_error: string | null; created_at: string;
};
export type Suppression = { id: string; kind: string; value_norm: string; reason: string; created_at: string };

export type Metric = { value: number | null; numerator: number | null; denominator: number | null; unit: string; definition: string; window: string };
export type Overview = { window: string; cards: Record<string, Metric>; funnel: { stage: string; count: number }[]; icp_distribution: { class: string; count: number }[] };
export type Campaign = {
  id: string; name: string; status: string; offer: string; objective: string; tone: string; sender_name: string; sender_company: string;
  physical_address: string; timezone: string; work_start: number; work_end: number; daily_limit: number; channels: string[];
  sequence: { step: number; day: number }[]; icp: Record<string, any>; thresholds: Record<string, number>; blocked_regions: string[];
  channel_account_id: string | null; lead_counts: Record<string, number>; message_counts: Record<string, number>;
};
export type Draft = {
  id: string; campaign_id: string; lead_id: string; channel: string; step: number; version: number; subject: string | null; body: string;
  rationale: string | null; claims: { text: string; evidence_id: string; quote: string }[]; quality: { errors: string[]; warnings: string[]; verified_claims: number; removed_claims: string[]; llm_note?: string | null };
  source: string; status: string; edited_since_approval?: boolean; evidence?: Evidence[];
  lead?: { id: string; name: string | null; title: string | null; email: string | null; company: string | null; domain: string | null; linkedin_url: string | null; instagram_url: string | null; region: string | null };
};
export type Account = { id: string; provider: string; name: string; from_email: string; status: string; daily_limit: number; health: Record<string, any>; simulated: boolean; capabilities: Record<string, boolean> };
