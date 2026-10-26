import { api } from "./api";

export type VoiceLanguage = "auto" | "en" | "hi" | "hinglish";
export type InsertMode = "cursor" | "append";

export type VoiceInfo = {
  enabled: boolean; provider: string | null; processing: "local" | "cloud" | null; cleanup_available: boolean;
  languages: { code: VoiceLanguage; label: string }[]; max_seconds: number; max_bytes: number; retention_hours: number; history_count: number;
};
export type VoiceResult = {
  id: string; status: "queued" | "processing" | "done" | "failed" | "cancelled" | "cleared"; language: VoiceLanguage;
  text: string | null; raw_text: string | null; cleaned: boolean; cleanup_requested: boolean; note: string | null;
  error_code: string | null; error_message: string | null; created_at: string | null;
};

/* ---------- text insertion: never deletes anything the user already wrote ---------- */

const NO_SPACE_BEFORE = /^[.,;:!?)\]}%।]/;

/** Insert `text` into `value`. "cursor" inserts after the current selection (a selection is kept, not replaced); "append" adds to the end. */
export function insertText(value: string, text: string, selStart: number, selEnd: number, mode: InsertMode, singleLine: boolean): { value: string; caret: number } {
  const clean = singleLine ? text.replace(/\s*\n+\s*/g, " ").trim() : text.trim();
  if (!clean) return { value, caret: Math.min(selEnd, value.length) };
  const pos = mode === "append" ? value.length : Math.max(0, Math.min(Math.max(selStart, selEnd), value.length));
  const before = value.slice(0, pos), after = value.slice(pos);
  const lead = before && !/\s$/.test(before) && !NO_SPACE_BEFORE.test(clean) ? " " : "";
  const trail = after && !/^\s/.test(after) && !NO_SPACE_BEFORE.test(after) ? " " : "";
  return { value: before + lead + clean + trail + after, caret: (before + lead + clean).length };
}

/* ---------- recording state machine ---------- */

export type VoiceState =
  | { name: "idle" }
  | { name: "recording" }
  | { name: "processing" }
  | { name: "review"; result: VoiceResult }
  | { name: "error"; code: string; message: string };

export type VoiceAction =
  | { type: "start" } | { type: "stop" } | { type: "cancel" } | { type: "ready"; result: VoiceResult }
  | { type: "fail"; code: string; message: string } | { type: "close" };

/** Only legal transitions are honoured; anything else is ignored so a stray event can never skip the review step. */
export function voiceReducer(state: VoiceState, a: VoiceAction): VoiceState {
  switch (a.type) {
    case "start": return state.name === "idle" || state.name === "error" ? { name: "recording" } : state;
    case "stop": return state.name === "recording" ? { name: "processing" } : state;
    case "cancel": return state.name === "recording" || state.name === "processing" ? { name: "idle" } : state;
    case "ready": return state.name === "processing" ? { name: "review", result: a.result } : state;
    case "fail": return state.name === "recording" || state.name === "processing" || state.name === "idle" ? { name: "error", code: a.code, message: a.message } : state;
    case "close": return state.name === "review" || state.name === "error" ? { name: "idle" } : state;
  }
}

/* ---------- microphone ---------- */

export function micError(err: unknown): { code: string; message: string } {
  const name = (err as { name?: string } | null)?.name;
  if (name === "NotAllowedError" || name === "SecurityError") return { code: "mic_denied", message: "Microphone access is blocked. Allow the microphone for this site in your browser's address-bar settings, then try again." };
  if (name === "NotFoundError" || name === "OverconstrainedError") return { code: "no_mic", message: "No microphone was found. Connect one and try again." };
  if (name === "NotReadableError" || name === "AbortError") return { code: "mic_busy", message: "The microphone could not be started. It may be in use by another app." };
  return { code: "mic_error", message: "Could not start the microphone. Your text was not changed." };
}

export function voiceSupport(): { ok: true } | { ok: false; code: string; message: string } {
  if (typeof window === "undefined") return { ok: false, code: "unsupported", message: "Voice input is not available here." };
  if (!navigator.mediaDevices?.getUserMedia) {
    return { ok: false, code: "insecure", message: window.isSecureContext === false ? "Voice input needs a secure (https) connection." : "This browser cannot access the microphone." };
  }
  if (typeof MediaRecorder === "undefined") return { ok: false, code: "unsupported", message: "This browser cannot record audio. Use a current Chrome, Edge, Firefox or Safari." };
  return { ok: true };
}

const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
export function pickMimeType(): string {
  try { return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m)) ?? ""; } catch { return ""; }
}

/* ---------- preferences (per browser; a convenience, never required) ---------- */

export type VoicePrefs = { language: VoiceLanguage; cleanup: boolean };
const PREFS_KEY = "flowhq-voice-prefs";
const DEFAULTS: VoicePrefs = { language: "auto", cleanup: true };
export function loadPrefs(): VoicePrefs {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}");
    return { language: ["auto", "en", "hi", "hinglish"].includes(p.language) ? p.language : DEFAULTS.language, cleanup: typeof p.cleanup === "boolean" ? p.cleanup : DEFAULTS.cleanup };
  } catch { return DEFAULTS; }
}
export function savePrefs(p: VoicePrefs) { try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); } catch { /* private mode */ } }

/* ---------- API ---------- */

export const getVoiceInfo = () => api<VoiceInfo>("/voice/status");
export const getVoice = (id: string) => api<VoiceResult>(`/voice/transcriptions/${id}`);
export const discardVoice = (id: string) => api<{ ok: boolean }>(`/voice/transcriptions/${id}`, { method: "DELETE" });
export const recentVoice = () => api<VoiceResult[]>("/voice/transcriptions");
export const clearVoiceHistory = () => api<{ cleared: number }>("/voice/transcriptions", { method: "DELETE" });

export function submitVoice(blob: Blob, o: { language: VoiceLanguage; cleanup: boolean; durationMs: number }) {
  const form = new FormData();
  form.set("file", blob, "dictation." + (blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm"));
  form.set("language", o.language); form.set("cleanup", String(o.cleanup)); form.set("duration_ms", String(Math.round(o.durationMs)));
  return api<VoiceResult>("/voice/transcriptions", { method: "POST", body: form });
}

export class VoiceTimeout extends Error {}

/** Poll until the dictation finishes. Throws VoiceTimeout, or the AbortError of `signal`. */
export async function waitForVoice(id: string, o: { signal: AbortSignal; intervalMs?: number; timeoutMs?: number; get?: (id: string) => Promise<VoiceResult> }): Promise<VoiceResult> {
  const { signal, intervalMs = 700, timeoutMs = 90_000, get = getVoice } = o;
  const t0 = Date.now();
  for (;;) {
    if (signal.aborted) throw new DOMException("aborted", "AbortError");
    const r = await get(id);
    if (r.status !== "queued" && r.status !== "processing") return r;
    if (Date.now() - t0 > timeoutMs) throw new VoiceTimeout("timeout");
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(resolve, intervalMs);
      signal.addEventListener("abort", () => { clearTimeout(t); reject(new DOMException("aborted", "AbortError")); }, { once: true });
    });
  }
}
