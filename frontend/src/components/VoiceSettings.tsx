"use client";
import { useCallback, useEffect, useState } from "react";
import { VoiceInfo, VoiceLanguage, VoiceResult, clearVoiceHistory, getVoiceInfo, recentVoice } from "@/lib/voice";
import { useVoicePrefs } from "./VoiceDictation";
import { Alert, Badge, Button, Card } from "./ui";

/** Integrations card: whether dictation is on, where speech is processed, defaults, and the user's own dictation history. */
export default function VoiceSettings() {
  const [info, setInfo] = useState<VoiceInfo | null | undefined>(undefined); const [recent, setRecent] = useState<VoiceResult[]>([]);
  const [prefs, setPrefs] = useVoicePrefs(); const [note, setNote] = useState<string | null>(null); const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { const i = await getVoiceInfo(); setInfo(i); setRecent(i.enabled ? await recentVoice() : []); } catch { setInfo(null); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function clear() {
    if (!window.confirm("Delete your dictation history from the server? Text already inserted into your forms is not affected.")) return;
    setError(null);
    try { const r = await clearVoiceHistory(); setNote(`Cleared ${r.cleared} dictation${r.cleared === 1 ? "" : "s"}.`); await load(); } catch (e) { setError((e as Error).message); }
  }

  return (
    <Card title="Voice dictation">
      {info === undefined ? <p className="text-sm text-muted-foreground">Loading…</p> : info === null ? <p className="text-sm text-muted-foreground">Could not load voice settings.</p> : (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={info.enabled ? "success" : "neutral"}>{info.enabled ? "on" : "off"}</Badge>
            {info.enabled && <span>{info.provider} · <b className="font-medium">{info.processing === "local" ? "processed on your own server" : "processed by an external service"}</b></span>}
          </div>
          {!info.enabled && <p className="text-muted-foreground">Set <code>STT_PROVIDER=openai_compat</code> with <code>STT_BASE_URL</code> pointing at a local Whisper-compatible server (or an authorised provider), then restart the API and worker. See the README.</p>}
          {info.enabled && (<>
            <p className="text-muted-foreground">Recording starts only when you press a microphone button. Raw audio is deleted as soon as it is transcribed, and nothing is ever sent for you: you review and insert the text yourself.
              {info.processing === "cloud" ? " Audio is sent to the external service to be transcribed." : " Audio never leaves your own server."} Transcripts are kept for {info.retention_hours} hours, then deleted automatically.</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block"><span className="mb-1 block text-xs font-medium">Default language</span>
                <select className="min-h-[44px] w-full rounded-lg border border-border bg-card px-2 text-sm md:min-h-9" value={prefs.language} onChange={(e) => setPrefs({ ...prefs, language: e.target.value as VoiceLanguage })}>
                  {info.languages.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}</select></label>
              <label className="flex items-start gap-2 pt-5"><input type="checkbox" className="mt-0.5 h-4 w-4" disabled={!info.cleanup_available} checked={prefs.cleanup && info.cleanup_available} onChange={(e) => setPrefs({ ...prefs, cleanup: e.target.checked })} />
                <span>Tidy up punctuation and filler words<span className="block text-xs text-muted-foreground">{info.cleanup_available ? "Numbers, links, emails and names are verified unchanged; otherwise the original is used." : "Needs a language model (LLM_PROVIDER); not set up."}</span></span></label>
            </div>
            {note && <Alert tone="success">{note}</Alert>}{error && <Alert>{error}</Alert>}
            <div>
              <div className="mb-1 flex items-center justify-between"><h3 className="text-sm font-semibold">Your recent dictations</h3>
                <Button variant="danger" disabled={recent.length === 0} onClick={clear}>Clear dictation history</Button></div>
              {recent.length === 0 ? <p className="text-xs text-muted-foreground">Nothing stored.</p> : (
                <ul className="divide-y divide-border text-xs">{recent.slice(0, 8).map((r) => (
                  <li key={r.id} className="flex justify-between gap-3 py-1.5"><span className="truncate" lang={r.language === "hi" ? "hi" : undefined}>{r.text}</span>
                    <time className="shrink-0 text-muted-foreground" dateTime={r.created_at ?? undefined}>{r.created_at ? new Date(r.created_at).toLocaleString() : ""}</time></li>))}</ul>)}
            </div>
          </>)}
        </div>)}
    </Card>
  );
}
