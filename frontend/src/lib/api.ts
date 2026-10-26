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
};
export type LeadDetail = Lead & {
  raw: Record<string, string>; lawful_basis: string | null;
  company: { name: string | null; domain: string | null; website: string | null } | null;
  timeline: { kind: string; at: string; data: Record<string, unknown> }[];
};
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
