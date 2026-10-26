import { afterEach, describe, expect, it, vi } from "vitest";
import {
  VoiceResult, VoiceState, VoiceTimeout, insertText, loadPrefs, micError, pickMimeType, savePrefs, voiceReducer, voiceSupport, waitForVoice,
} from "./voice";

describe("insertText", () => {
  it("inserts at the cursor with sensible spacing", () => {
    expect(insertText("Hello world", "big", 5, 5, "cursor", false)).toEqual({ value: "Hello big world", caret: 9 });
    expect(insertText("", "Hello", 0, 0, "cursor", false)).toEqual({ value: "Hello", caret: 5 });
    expect(insertText("Hello ", "world", 6, 6, "cursor", false).value).toBe("Hello world");
  });

  it("never deletes the user's selection: text goes after it", () => {
    const out = insertText("Hello world", "again", 6, 11, "cursor", false);
    expect(out.value).toBe("Hello world again");
    expect(out.value).toContain("world");
  });

  it("appends to the end regardless of the cursor", () => {
    expect(insertText("Hello world", "again", 0, 0, "append", false).value).toBe("Hello world again");
    expect(insertText("Line one\n", "Line two", 0, 0, "append", false).value).toBe("Line one\nLine two");
  });

  it("does not put a space before punctuation", () => {
    expect(insertText("Hello", ", world", 5, 5, "cursor", false).value).toBe("Hello, world");
    expect(insertText("Pay now", "।", 7, 7, "cursor", false).value).toBe("Pay now।");
  });

  it("collapses newlines for single-line fields only", () => {
    expect(insertText("", "one\n\ntwo", 0, 0, "cursor", true).value).toBe("one two");
    expect(insertText("", "one\n\ntwo", 0, 0, "cursor", false).value).toBe("one\n\ntwo");
  });

  it("leaves the value alone for empty text and clamps wild cursor positions", () => {
    expect(insertText("keep me", "   ", 3, 3, "cursor", false).value).toBe("keep me");
    expect(insertText("abc", "x", 99, 99, "cursor", false).value).toBe("abc x");
    expect(insertText("abc", "x", -5, -5, "cursor", false).value).toBe("x abc");
  });

  it("keeps Hindi and Hinglish text intact", () => {
    expect(insertText("Note:", "कल 3 बजे फोन करना है", 5, 5, "cursor", false).value).toBe("Note: कल 3 बजे फोन करना है");
    expect(insertText("", "kal 3 baje call karna hai", 0, 0, "cursor", false).value).toBe("kal 3 baje call karna hai");
  });

  it("always preserves everything that was already there", () => {
    for (const [v, s, e, mode] of [["alpha beta gamma", 6, 10, "cursor"], ["alpha beta gamma", 0, 0, "cursor"], ["alpha beta gamma", 16, 16, "cursor"], ["alpha beta gamma", 3, 3, "append"]] as const) {
      const out = insertText(v, "NEW TEXT", s, e, mode, false).value;
      expect(out.replace("NEW TEXT", "").replace(/\s+/g, " ").trim()).toBe(v);
    }
  });
});

const R = { id: "1", status: "done", language: "en", text: "hi", raw_text: "hi", cleaned: false, cleanup_requested: false, note: null, error_code: null, error_message: null, created_at: null } as VoiceResult;

describe("voiceReducer", () => {
  const run = (...actions: Parameters<typeof voiceReducer>[1][]) => actions.reduce<VoiceState>(voiceReducer, { name: "idle" });

  it("walks idle -> recording -> processing -> review -> idle", () => {
    expect(run({ type: "start" }).name).toBe("recording");
    expect(run({ type: "start" }, { type: "stop" }).name).toBe("processing");
    expect(run({ type: "start" }, { type: "stop" }, { type: "ready", result: R }).name).toBe("review");
    expect(run({ type: "start" }, { type: "stop" }, { type: "ready", result: R }, { type: "close" }).name).toBe("idle");
  });

  it("cannot reach review without recording and processing first", () => {
    expect(run({ type: "ready", result: R }).name).toBe("idle");
    expect(run({ type: "start" }, { type: "ready", result: R }).name).toBe("recording");
    expect(run({ type: "stop" }).name).toBe("idle");
  });

  it("cancel returns to idle from recording and processing, and is ignored in review", () => {
    expect(run({ type: "start" }, { type: "cancel" }).name).toBe("idle");
    expect(run({ type: "start" }, { type: "stop" }, { type: "cancel" }).name).toBe("idle");
    expect(run({ type: "start" }, { type: "stop" }, { type: "ready", result: R }, { type: "cancel" }).name).toBe("review");
  });

  it("failures surface as an error that can be dismissed or retried", () => {
    const e = run({ type: "start" }, { type: "fail", code: "mic_denied", message: "blocked" });
    expect(e).toEqual({ name: "error", code: "mic_denied", message: "blocked" });
    expect(voiceReducer(e, { type: "start" }).name).toBe("recording");
    expect(voiceReducer(e, { type: "close" }).name).toBe("idle");
  });

  it("a second start while busy does not restart", () => {
    expect(run({ type: "start" }, { type: "start" }, { type: "stop" }, { type: "start" }).name).toBe("processing");
  });
});

describe("microphone and browser support", () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it.each([
    ["NotAllowedError", "mic_denied"], ["SecurityError", "mic_denied"], ["NotFoundError", "no_mic"], ["OverconstrainedError", "no_mic"],
    ["NotReadableError", "mic_busy"], ["AbortError", "mic_busy"], ["WeirdError", "mic_error"],
  ])("maps %s to %s", (name, code) => {
    const m = micError({ name });
    expect(m.code).toBe(code);
    expect(m.message.length).toBeGreaterThan(20);
  });

  it("explains how to recover from a blocked microphone", () => {
    expect(micError({ name: "NotAllowedError" }).message).toMatch(/address-bar|browser/i);
  });

  it("reports missing getUserMedia and missing MediaRecorder separately", () => {
    vi.stubGlobal("MediaRecorder", class {});
    Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true });
    expect(voiceSupport()).toMatchObject({ ok: false, code: "insecure" });
    Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia: vi.fn() }, configurable: true });
    vi.stubGlobal("MediaRecorder", undefined);
    expect(voiceSupport()).toMatchObject({ ok: false, code: "unsupported" });
    vi.stubGlobal("MediaRecorder", class {});
    expect(voiceSupport()).toEqual({ ok: true });
  });

  it("picks the first container the browser can record", () => {
    vi.stubGlobal("MediaRecorder", { isTypeSupported: (m: string) => m === "audio/mp4" });
    expect(pickMimeType()).toBe("audio/mp4");
    vi.stubGlobal("MediaRecorder", { isTypeSupported: () => true });
    expect(pickMimeType()).toBe("audio/webm;codecs=opus");
    vi.stubGlobal("MediaRecorder", { isTypeSupported: () => false });
    expect(pickMimeType()).toBe("");
  });
});

describe("preferences", () => {
  afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

  it("round-trips and rejects garbage", () => {
    savePrefs({ language: "hinglish", cleanup: false });
    expect(loadPrefs()).toEqual({ language: "hinglish", cleanup: false });
    localStorage.setItem("flowhq-voice-prefs", JSON.stringify({ language: "klingon", cleanup: "yes" }));
    expect(loadPrefs()).toEqual({ language: "auto", cleanup: true });
    localStorage.setItem("flowhq-voice-prefs", "{not json");
    expect(loadPrefs()).toEqual({ language: "auto", cleanup: true });
  });

  it("works when storage is unavailable", () => {
    vi.stubGlobal("localStorage", { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } });
    expect(loadPrefs()).toEqual({ language: "auto", cleanup: true });
    expect(() => savePrefs({ language: "en", cleanup: true })).not.toThrow();
  });
});

describe("waitForVoice", () => {
  const status = (s: VoiceResult["status"]) => ({ ...R, status: s });

  it("polls until the dictation finishes", async () => {
    const get = vi.fn().mockResolvedValueOnce(status("queued")).mockResolvedValueOnce(status("processing")).mockResolvedValueOnce(status("done"));
    const r = await waitForVoice("1", { signal: new AbortController().signal, intervalMs: 1, get });
    expect(r.status).toBe("done");
    expect(get).toHaveBeenCalledTimes(3);
  });

  it("returns failures too, so the caller can show the reason", async () => {
    const get = vi.fn().mockResolvedValue({ ...status("failed"), error_code: "no_speech" });
    expect((await waitForVoice("1", { signal: new AbortController().signal, intervalMs: 1, get })).error_code).toBe("no_speech");
  });

  it("times out", async () => {
    const get = vi.fn().mockResolvedValue(status("processing"));
    await expect(waitForVoice("1", { signal: new AbortController().signal, intervalMs: 5, timeoutMs: 30, get })).rejects.toBeInstanceOf(VoiceTimeout);
  });

  it("stops promptly when aborted", async () => {
    const ac = new AbortController();
    const get = vi.fn().mockResolvedValue(status("processing"));
    const p = waitForVoice("1", { signal: ac.signal, intervalMs: 1000, get });
    setTimeout(() => ac.abort(), 10);
    await expect(p).rejects.toMatchObject({ name: "AbortError" });
  });

  it("propagates network errors", async () => {
    await expect(waitForVoice("1", { signal: new AbortController().signal, get: vi.fn().mockRejectedValue(new TypeError("offline")) })).rejects.toThrow("offline");
  });
});
