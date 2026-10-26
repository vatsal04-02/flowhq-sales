"use client";
import { cloneElement, isValidElement, useCallback, useEffect, useId, useReducer, useRef, useState, useSyncExternalStore } from "react";
import type { ReactElement, ReactNode } from "react";
import { createPortal } from "react-dom";
import { ApiError } from "@/lib/api";
import {
  InsertMode, VoiceInfo, VoiceLanguage, VoicePrefs, VoiceResult, VoiceTimeout, discardVoice, getVoiceInfo, insertText, loadPrefs, micError,
  pickMimeType, savePrefs, submitVoice, voiceReducer, voiceSupport, waitForVoice,
} from "@/lib/voice";
import { Icon, cx } from "./ui";

type Target = HTMLInputElement | HTMLTextAreaElement;
const MIN_BYTES = 800, MIN_MS = 400;

/* ---------- preferences and server info, shared by every mic button on the page ---------- */
const SERVER_PREFS: VoicePrefs = { language: "auto", cleanup: true };
let prefsNow: VoicePrefs | null = null;
const prefsListeners = new Set<() => void>();
const subscribePrefs = (l: () => void) => { prefsListeners.add(l); return () => { prefsListeners.delete(l); }; };
const readPrefs = () => (prefsNow ??= loadPrefs());
function writePrefs(p: VoicePrefs) { prefsNow = p; savePrefs(p); prefsListeners.forEach((l) => l()); }
export function useVoicePrefs(): [VoicePrefs, (p: VoicePrefs) => void] {
  return [useSyncExternalStore(subscribePrefs, readPrefs, () => SERVER_PREFS), writePrefs];
}

let infoPromise: Promise<VoiceInfo | null> | null = null;
export function resetVoiceCaches() { prefsNow = null; infoPromise = null; }
export function useVoiceInfo(): VoiceInfo | null | undefined {
  const [info, setInfo] = useState<VoiceInfo | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    (infoPromise ??= getVoiceInfo().catch(() => null)).then((i) => live && setInfo(i));
    return () => { live = false; };
  }, []);
  return info;
}

/* ---------- field wrapper ---------- */

/** Wrap any single text input or textarea to add dictation. `value`/`onChange` are the same controlled state the field already uses. */
export function Dictatable({ label, value, onChange, children, className, disabled }: { label: string; value: string; onChange: (v: string) => void; children: ReactNode; className?: string; disabled?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const getTarget = useCallback(() => box.current?.querySelector<Target>("textarea, input") ?? null, []);
  return (
    <div ref={box} className={cx("relative", !disabled && "[&_input]:pr-16 [&_textarea]:pr-16", className)}>
      {children}
      {!disabled && <VoiceDictation label={label} getTarget={getTarget} value={value} onChange={onChange} />}
    </div>
  );
}

/** A labelled field with dictation. The label is a sibling of the control (linked by htmlFor), never a wrapper around it, so the
 *  microphone buttons are not folded into the field's accessible name ("Offer Dictate offer Dictation settings…"). */
export function DictatedField({ label, speak, hint, value, onChange, disabled, className, children }: {
  label: string; speak: string; hint?: string; value: string; onChange: (v: string) => void; disabled?: boolean; className?: string; children: ReactElement;
}) {
  const id = useId(); const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className={cx("block text-sm", className)}>
      <label htmlFor={id} className="mb-1 block font-medium">{label}</label>
      <Dictatable label={speak} value={value} onChange={onChange} disabled={disabled}>
        {isValidElement(children) ? cloneElement(children as ReactElement<Record<string, unknown>>, { id, "aria-describedby": hintId }) : children}
      </Dictatable>
      {hint && <span id={hintId} className="mt-1 block text-xs text-muted-foreground">{hint}</span>}
    </div>
  );
}

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/* ---------- the control ---------- */

export default function VoiceDictation({ label, getTarget, value, onChange }: { label: string; getTarget: () => Target | null; value: string; onChange: (v: string) => void }) {
  const info = useVoiceInfo(); const [prefs, setPrefs] = useVoicePrefs();
  const [state, dispatch] = useReducer(voiceReducer, { name: "idle" });
  const [live, setLive] = useState(false); const [elapsed, setElapsed] = useState(0);
  const [announce, setAnnounce] = useState(""); const [menu, setMenu] = useState(false);
  const r = useRef({ rec: null as MediaRecorder | null, stream: null as MediaStream | null, chunks: [] as Blob[], startedAt: 0, cancelled: false, abort: null as AbortController | null, id: null as string | null });
  const latest = useRef({ value, onChange, prefs, info }); latest.current = { value, onChange, prefs, info };
  const micRef = useRef<HTMLButtonElement>(null); const menuBtn = useRef<HTMLButtonElement>(null);

  const release = () => { r.current.stream?.getTracks().forEach((t) => t.stop()); r.current.stream = null; };
  const fail = (code: string, message: string) => { setLive(false); dispatch({ type: "fail", code, message }); setAnnounce(message); };

  async function start() {
    if (latest.current.info?.enabled === false) return fail("voice_disabled", "Voice input is not set up on this server. Ask an admin to configure a speech service.");
    const sup = voiceSupport(); if (!sup.ok) return fail(sup.code, sup.message);
    const c = r.current; c.cancelled = false; c.id = null; c.chunks = [];
    dispatch({ type: "start" }); setMenu(false); setElapsed(0);
    let stream: MediaStream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }   // the only place the microphone is requested
    catch (e) { const m = micError(e); return fail(m.code, m.message); }
    if (c.cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }       // cancelled while the permission prompt was open
    c.stream = stream;
    try {
      const mime = pickMimeType(); const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined); c.rec = rec;
      rec.ondataavailable = (e) => { if (e.data && e.data.size) c.chunks.push(e.data); };
      rec.onstop = () => {
        release(); setLive(false);
        if (c.cancelled) return;
        void finish(new Blob(c.chunks, { type: rec.mimeType || mime || "audio/webm" }), Date.now() - c.startedAt);
      };
      rec.onerror = () => { release(); fail("mic_error", "Recording failed. Your text was not changed."); };
      rec.start(250); c.startedAt = Date.now(); setLive(true); setAnnounce(`Recording ${label}. Press Stop when you are done, or Escape to cancel.`);
    } catch { release(); fail("unsupported", "This browser could not start recording. Your text was not changed."); }
  }

  function stop() {
    const rec = r.current.rec; if (!rec || rec.state === "inactive") return;
    dispatch({ type: "stop" }); setAnnounce("Recording stopped. Transcribing."); rec.stop();
  }

  function cancel() {
    const c = r.current; c.cancelled = true; c.abort?.abort();
    if (c.rec && c.rec.state !== "inactive") { try { c.rec.stop(); } catch { /* already stopped */ } }
    release(); setLive(false);
    if (c.id) discardVoice(c.id).catch(() => {});                                       // the server drops audio and text right away
    dispatch({ type: "cancel" }); setAnnounce("Dictation cancelled. Nothing was changed.");
    micRef.current?.focus();
  }

  async function finish(blob: Blob, durationMs: number) {
    const c = r.current;
    if (blob.size < MIN_BYTES || durationMs < MIN_MS) return fail("empty_recording", "That recording was empty. Press the microphone, speak, then press Stop.");
    const ac = (c.abort = new AbortController());
    try {
      const { prefs: p, info: i } = latest.current;
      const up = await submitVoice(blob, { language: p.language, cleanup: p.cleanup && !!i?.cleanup_available, durationMs });
      c.id = up.id;
      if (c.cancelled) { discardVoice(up.id).catch(() => {}); return; }
      const res = await waitForVoice(up.id, { signal: ac.signal });
      if (c.cancelled) return;
      if (res.status === "done" && res.text) { dispatch({ type: "ready", result: res }); setAnnounce("Transcript ready for review."); }
      else fail(res.error_code ?? "failed", res.error_message ?? "Transcription failed. Your text was not changed.");
    } catch (e) {
      if (c.cancelled || (e as Error)?.name === "AbortError") return;
      if (e instanceof VoiceTimeout) { if (c.id) discardVoice(c.id).catch(() => {}); return fail("timeout", "Transcription is taking too long. Your text was not changed; try again."); }
      if (e instanceof ApiError) return fail(e.code, e.message);
      fail("network", "Could not reach the server. Your text was not changed.");
    }
  }

  function insert(text: string, mode: InsertMode) {
    const t = getTarget(); const { value: cur, onChange: set } = latest.current; let s = cur.length, e = cur.length;
    try { s = t?.selectionStart ?? cur.length; e = t?.selectionEnd ?? s; } catch { /* input types without a selection */ }
    const out = insertText(cur, text, s, e, mode, t instanceof HTMLInputElement);
    set(out.value); dispatch({ type: "close" }); setAnnounce("Dictation inserted. Review it before saving or sending.");
    requestAnimationFrame(() => { t?.focus(); try { t?.setSelectionRange(out.caret, out.caret); } catch { /* ignore */ } });
  }

  function discard() {
    if (state.name === "review" && r.current.id) discardVoice(r.current.id).catch(() => {});
    dispatch({ type: "close" }); setAnnounce("Dictation discarded."); micRef.current?.focus();
  }

  // elapsed timer + automatic stop at the server's limit
  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => {
      const s = Math.floor((Date.now() - r.current.startedAt) / 1000); setElapsed(s);
      if (s >= (latest.current.info?.max_seconds ?? 120)) stop();
    }, 250);
    return () => clearInterval(t);
  }, [live]);                                                                             // eslint-disable-line react-hooks/exhaustive-deps

  // Escape cancels an active dictation
  useEffect(() => {
    if (state.name !== "recording" && state.name !== "processing") return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") cancel(); };
    document.addEventListener("keydown", onKey); return () => document.removeEventListener("keydown", onKey);
  }, [state.name]);                                                                       // eslint-disable-line react-hooks/exhaustive-deps

  // leaving the page must release the microphone and drop anything in flight
  useEffect(() => () => {
    const c = r.current; c.cancelled = true; c.abort?.abort();
    if (c.rec && c.rec.state !== "inactive") { try { c.rec.stop(); } catch { /* ignore */ } }
    c.stream?.getTracks().forEach((t) => t.stop()); if (c.id) discardVoice(c.id).catch(() => {});
  }, []);

  const langLabel = info?.languages.find((l) => l.code === prefs.language)?.label ?? "Detect automatically";
  const active = state.name === "recording" || state.name === "processing";
  return (
    <>
      <span className="sr-only" role="status" aria-live="polite">{announce}</span>
      {!active && (
        <div className="absolute right-1 top-1 z-10 flex items-center rounded-md">
          <button ref={micRef} type="button" onClick={() => void start()} aria-label={`Dictate ${label}`} title={`Dictate (${langLabel})`}
            aria-disabled={info?.enabled === false || undefined}
            className={cx("grid h-9 w-9 cursor-pointer place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground md:h-7 md:w-7", info?.enabled === false && "opacity-50")}>
            <Icon name="mic" className="h-4 w-4" />
          </button>
          <button ref={menuBtn} type="button" onClick={() => setMenu((m) => !m)} aria-label={`Dictation settings for ${label}`} aria-haspopup="dialog" aria-expanded={menu}
            className="grid h-9 w-5 cursor-pointer place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground md:h-7">
            <Icon name="chevron" className="h-3 w-3" />
          </button>
        </div>)}
      {state.name === "recording" && (
        <div className="absolute right-1 top-1 z-10 flex items-center gap-1 rounded-md border border-destructive/40 bg-card py-0.5 pl-2 pr-0.5 text-xs shadow-card" data-testid="recording-indicator">
          {live ? <><span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-destructive" /><span className="tabular-nums" aria-label="Recording time">{fmt(elapsed)}</span></> : <span>Allow microphone…</span>}
          <button type="button" onClick={stop} disabled={!live} aria-label="Stop and transcribe" className="grid h-8 w-8 cursor-pointer place-items-center rounded text-destructive hover:bg-destructive/10 disabled:opacity-40 md:h-7 md:w-7"><Icon name="square" className="h-4 w-4" /></button>
          <button type="button" onClick={cancel} aria-label="Cancel and discard recording" className="grid h-8 w-8 cursor-pointer place-items-center rounded text-muted-foreground hover:bg-muted md:h-7 md:w-7"><Icon name="x" className="h-4 w-4" /></button>
        </div>)}
      {state.name === "processing" && (
        <div className="absolute right-1 top-1 z-10 flex items-center gap-1.5 rounded-md border border-border bg-card py-0.5 pl-2 pr-0.5 text-xs shadow-card" data-testid="processing-indicator">
          <span aria-hidden="true" className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" /><span>Transcribing…</span>
          <button type="button" onClick={cancel} aria-label="Cancel transcription" className="grid h-8 w-8 cursor-pointer place-items-center rounded text-muted-foreground hover:bg-muted md:h-7 md:w-7"><Icon name="x" className="h-4 w-4" /></button>
        </div>)}
      {state.name === "error" && (
        <div role="alert" className="absolute right-0 top-full z-20 mt-1 flex max-w-xs items-start gap-2 rounded-lg border border-destructive/40 bg-card p-2.5 text-xs shadow-lift">
          <Icon name="alert" className="mt-0.5 h-3.5 w-3.5 text-destructive" /><span className="flex-1">{state.message}</span>
          <button type="button" onClick={() => dispatch({ type: "close" })} aria-label="Dismiss" className="cursor-pointer text-muted-foreground hover:text-foreground"><Icon name="x" className="h-3.5 w-3.5" /></button>
        </div>)}
      {menu && <SettingsMenu anchor={menuBtn.current} info={info} prefs={prefs} setPrefs={setPrefs} onClose={() => { setMenu(false); menuBtn.current?.focus(); }} />}
      {state.name === "review" && <ReviewDialog result={state.result} label={label} info={info} onInsert={insert} onDiscard={discard} />}
    </>
  );
}

/* ---------- popover with language and cleanup ---------- */

function SettingsMenu({ anchor, info, prefs, setPrefs, onClose }: { anchor: HTMLElement | null; info: VoiceInfo | null | undefined; prefs: VoicePrefs; setPrefs: (p: VoicePrefs) => void; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null); const id = useId();
  const rect = anchor?.getBoundingClientRect();
  useEffect(() => {
    const down = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node) && !anchor?.contains(e.target as Node)) onClose(); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", down); document.addEventListener("keydown", key);
    ref.current?.querySelector("select")?.focus();
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("keydown", key); };
  }, []);                                                                                 // eslint-disable-line react-hooks/exhaustive-deps
  const langs = info?.languages ?? [{ code: "auto" as const, label: "Detect automatically" }, { code: "en" as const, label: "English" }, { code: "hi" as const, label: "Hindi (Devanagari)" }, { code: "hinglish" as const, label: "Hinglish (Hindi in Roman letters)" }];
  const where = info?.processing === "local" ? "Speech is processed on your own server." : info?.processing === "cloud" ? "Audio is sent to an external speech service and deleted right after transcription." : "";
  return createPortal(
    <div ref={ref} role="dialog" aria-label="Dictation settings" style={{ position: "fixed", top: (rect?.bottom ?? 0) + 6, left: Math.max(8, (rect?.right ?? 280) - 280), width: 272 }}
      className="z-50 space-y-3 rounded-xl border border-border bg-card p-3 text-sm shadow-lift">
      <div><label htmlFor={`${id}-lang`} className="mb-1 block text-xs font-medium">Language</label>
        <select id={`${id}-lang`} value={prefs.language} onChange={(e) => setPrefs({ ...prefs, language: e.target.value as VoiceLanguage })} className="min-h-9 w-full rounded-lg border border-border bg-card px-2 text-sm">
          {langs.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}</select></div>
      <div className="flex items-start gap-2"><input id={`${id}-clean`} type="checkbox" className="mt-0.5 h-4 w-4" checked={prefs.cleanup && !!info?.cleanup_available} disabled={!info?.cleanup_available}
        onChange={(e) => setPrefs({ ...prefs, cleanup: e.target.checked })} />
        <label htmlFor={`${id}-clean`} className="text-xs leading-snug">Tidy up punctuation and filler words<span className="block text-muted-foreground">{info?.cleanup_available ? "Numbers, links, emails and names are verified unchanged." : "Needs a language model; not set up here."}</span></label></div>
      {where && <p className="border-t border-border pt-2 text-xs text-muted-foreground">{where} Raw audio is never kept.</p>}
    </div>, document.body);
}

/* ---------- review: nothing leaves this dialog except the text the user chooses to insert ---------- */

function ReviewDialog({ result, label, info, onInsert, onDiscard }: { result: VoiceResult; label: string; info: VoiceInfo | null | undefined; onInsert: (t: string, m: InsertMode) => void; onDiscard: () => void }) {
  const hasTidy = result.cleaned && !!result.raw_text && result.raw_text !== result.text;
  const [variant, setVariant] = useState<"tidy" | "original">(hasTidy ? "tidy" : "original");
  const [drafts, setDrafts] = useState({ tidy: result.text ?? "", original: (hasTidy ? result.raw_text : result.text) ?? "" });   // edits are kept per version, never silently lost
  const [mode, setMode] = useState<InsertMode>("cursor");
  const box = useRef<HTMLDivElement>(null); const area = useRef<HTMLTextAreaElement>(null); const id = useId();
  const text = drafts[variant];
  useEffect(() => { area.current?.focus(); }, []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onDiscard(); }
      if (e.key === "Tab") {                                                                // keep focus inside the dialog
        const f = box.current?.querySelectorAll<HTMLElement>("button, textarea, input, select"); if (!f?.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", key); return () => document.removeEventListener("keydown", key);
  }, []);                                                                                   // eslint-disable-line react-hooks/exhaustive-deps
  const seg = (v: "tidy" | "original", name: string) => (
    <button type="button" role="radio" aria-checked={variant === v} onClick={() => setVariant(v)}
      className={cx("min-h-9 cursor-pointer rounded-md px-3 text-xs font-medium", variant === v ? "bg-card shadow-card" : "text-muted-foreground hover:text-foreground")}>{name}</button>);
  return createPortal(
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4">
      <div ref={box} role="dialog" aria-modal="true" aria-labelledby={`${id}-t`} className="w-full max-w-lg space-y-3 rounded-2xl border border-border bg-card p-5 shadow-lift">
        <div><h2 id={`${id}-t`} className="text-lg">Review your dictation</h2>
          <p className="text-sm text-muted-foreground">Edit it if needed, then insert it into <b className="font-medium text-foreground">{label}</b>. Nothing is sent or saved until you do that yourself.</p></div>
        {hasTidy && <div role="radiogroup" aria-label="Version" className="inline-flex gap-0.5 rounded-lg bg-muted p-0.5">{seg("tidy", "Tidied up")}{seg("original", "Original")}</div>}
        <textarea ref={area} aria-label="Transcript" lang={result.language === "hi" ? "hi" : undefined} rows={6} value={text}
          onChange={(e) => setDrafts((d) => ({ ...d, [variant]: e.target.value }))} className="min-h-[8rem] w-full rounded-lg border border-border bg-card px-3 py-2 text-sm" />
        {result.cleaned && variant === "tidy" && <p className="text-xs text-muted-foreground">Tidied up automatically. Numbers, links, emails and names were checked and are unchanged.</p>}
        {result.note && <p className="text-xs text-muted-foreground" data-testid="voice-note">{result.note}</p>}
        <fieldset className="flex flex-wrap gap-x-4 gap-y-1 text-sm"><legend className="sr-only">Where to put it</legend>
          {([["cursor", "At the cursor"], ["append", "Add to the end"]] as const).map(([m, name]) => (
            <label key={m} className="flex min-h-[32px] cursor-pointer items-center gap-1.5"><input type="radio" name={`${id}-mode`} checked={mode === m} onChange={() => setMode(m)} />{name}</label>))}
          <span className="basis-full text-xs text-muted-foreground">Existing text is never replaced.</span></fieldset>
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <p className="max-w-[16rem] text-xs text-muted-foreground">{info?.processing === "cloud" ? "Audio was sent to an external speech service and deleted afterwards." : "Processed on your own server. Raw audio is not kept."}</p>
          <div className="flex gap-2"><button type="button" onClick={onDiscard} className="min-h-[44px] cursor-pointer rounded-lg border border-border bg-card px-3.5 text-sm font-medium shadow-card hover:bg-muted md:min-h-9">Discard</button>
            <button type="button" disabled={!text.trim()} onClick={() => onInsert(text, mode)} className="min-h-[44px] cursor-pointer rounded-lg bg-primary px-3.5 text-sm font-medium text-primary-foreground shadow-card hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50 md:min-h-9">Insert</button></div>
        </div>
      </div>
    </div>, document.body);
}
