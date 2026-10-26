import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import * as V from "@/lib/voice";
import { DictatedField, Dictatable, resetVoiceCaches } from "./VoiceDictation";

vi.mock("@/lib/voice", async (orig) => {
  const actual = await orig<typeof import("@/lib/voice")>();
  return { ...actual, getVoiceInfo: vi.fn(), submitVoice: vi.fn(), waitForVoice: vi.fn(), discardVoice: vi.fn() };
});
const m = vi.mocked(V);

const INFO: V.VoiceInfo = {
  enabled: true, provider: "stt:test", processing: "local", cleanup_available: true, max_seconds: 120, max_bytes: 10_000_000, retention_hours: 24, history_count: 0,
  languages: [{ code: "auto", label: "Detect automatically" }, { code: "en", label: "English" }, { code: "hi", label: "Hindi (Devanagari)" }, { code: "hinglish", label: "Hinglish (Hindi in Roman letters)" }],
};
const RESULT: V.VoiceResult = {
  id: "v1", status: "done", language: "auto", text: "call Rohan at 5 pm", raw_text: "call Rohan at 5 pm", cleaned: false, cleanup_requested: false,
  note: null, error_code: null, error_message: null, created_at: null,
};

let now = 1_000_000;
const tracks = [{ stop: vi.fn() }];
let recorder: FakeRecorder | null = null;
class FakeRecorder {
  static isTypeSupported = () => true;
  state = "inactive"; mimeType = "audio/webm"; bytes = 3000;
  ondataavailable: ((e: { data: Blob }) => void) | null = null; onstop: (() => void) | null = null; onerror: (() => void) | null = null;
  constructor(public stream: unknown) { recorder = this; }
  start() { this.state = "recording"; }
  stop() { this.state = "inactive"; this.ondataavailable?.({ data: new Blob([new Uint8Array(this.bytes)]) }); this.onstop?.(); }
}

function media(deny?: string) {
  const getUserMedia = vi.fn(async () => { if (deny) throw Object.assign(new Error("denied"), { name: deny }); return { getTracks: () => tracks } as unknown as MediaStream; });
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  return getUserMedia;
}

function Harness({ initial = "Hello world", onSubmit = vi.fn(), single = false, disabled = false }: { initial?: string; onSubmit?: () => void; single?: boolean; disabled?: boolean }) {
  const [v, setV] = useState(initial);
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
      <Dictatable label="offer" value={v} onChange={setV} disabled={disabled}>
        {single ? <input aria-label="Offer" value={v} onChange={(e) => setV(e.target.value)} /> : <textarea aria-label="Offer" value={v} onChange={(e) => setV(e.target.value)} />}
      </Dictatable>
    </form>);
}

async function setup(ui = <Harness />, info: Partial<V.VoiceInfo> | null = {}) {
  m.getVoiceInfo.mockImplementation(async () => { if (info === null) throw new Error("down"); return { ...INFO, ...info }; });
  const user = userEvent.setup();
  const view = render(ui);
  await waitFor(() => expect(m.getVoiceInfo).toHaveBeenCalled());
  await act(async () => {});
  return { user, view, field: () => screen.getByLabelText("Offer") as HTMLTextAreaElement | HTMLInputElement };
}

const mic = () => screen.getByRole("button", { name: "Dictate offer" });
async function record(user: ReturnType<typeof userEvent.setup>, ms = 3000) {
  await user.click(mic());
  const stop = await screen.findByRole("button", { name: "Stop and transcribe" });
  await waitFor(() => expect(stop).toBeEnabled());
  now += ms;
  await user.click(stop);
}
const dialog = () => screen.getByRole("dialog", { name: /review your dictation/i });

beforeEach(() => {
  resetVoiceCaches(); localStorage.clear(); tracks[0].stop.mockClear(); recorder = null; now = 1_000_000;
  vi.spyOn(Date, "now").mockImplementation(() => now);
  media();
  m.submitVoice.mockImplementation(async () => ({ ...RESULT, status: "queued", text: null, raw_text: null }));
  m.waitForVoice.mockImplementation(async () => RESULT);
  m.discardVoice.mockImplementation(async () => ({ ok: true }));
});

describe("permissions", () => {
  it("does not touch the microphone until the user activates dictation", async () => {
    const getUserMedia = media();
    await setup();
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(screen.queryByTestId("recording-indicator")).toBeNull();
  });

  it("asks for the microphone exactly once, when the button is pressed", async () => {
    const getUserMedia = media();
    const { user } = await setup();
    await user.click(mic());
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(1));
  });

  it("shows a clear message when permission is denied and leaves the field untouched", async () => {
    media("NotAllowedError");
    const { user, field } = await setup();
    await user.click(mic());
    expect(await screen.findByRole("alert")).toHaveTextContent(/microphone access is blocked/i);
    expect(field().value).toBe("Hello world");
    expect(screen.queryByTestId("recording-indicator")).toBeNull();
    expect(m.submitVoice).not.toHaveBeenCalled();
  });

  it("can be retried after a denial", async () => {
    media("NotAllowedError");
    const { user } = await setup();
    await user.click(mic());
    await screen.findByRole("alert");
    media();
    await user.click(mic());
    expect(await screen.findByTestId("recording-indicator")).toBeInTheDocument();
  });

  it.each([["NotFoundError", /no microphone was found/i], ["NotReadableError", /in use by another app/i]])("explains %s", async (name, text) => {
    media(name);
    const { user } = await setup();
    await user.click(mic());
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
  });

  it("explains when the browser cannot record at all", async () => {
    Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true });
    const { user } = await setup();
    await user.click(mic());
    expect(await screen.findByRole("alert")).toHaveTextContent(/secure|cannot access the microphone/i);
  });

  it("says so when the server has no speech service, without asking for the microphone", async () => {
    const getUserMedia = media();
    const { user } = await setup(<Harness />, { enabled: false });
    expect(mic()).toHaveAttribute("aria-disabled", "true");
    await user.click(mic());
    expect(await screen.findByRole("alert")).toHaveTextContent(/not set up on this server/i);
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it("renders no microphone at all for a disabled field", async () => {
    render(<Harness disabled />);
    await act(async () => {});
    expect(screen.queryByRole("button", { name: "Dictate offer" })).toBeNull();
    expect(m.getVoiceInfo).not.toHaveBeenCalled();
  });
});

describe("recording states", () => {
  it("shows a visible recording indicator with a timer, stop and cancel", async () => {
    const { user } = await setup();
    await user.click(mic());
    const indicator = await screen.findByTestId("recording-indicator");
    expect(within(indicator).getByRole("button", { name: "Stop and transcribe" })).toBeInTheDocument();
    expect(within(indicator).getByRole("button", { name: "Cancel and discard recording" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/recording offer/i);
  });

  it("moves recording -> processing -> review and releases the microphone", async () => {
    let finish!: (r: V.VoiceResult) => void;
    m.waitForVoice.mockImplementation(() => new Promise((r) => { finish = r; }));
    const { user } = await setup();
    await record(user);
    expect(await screen.findByTestId("processing-indicator")).toBeInTheDocument();
    expect(tracks[0].stop).toHaveBeenCalled();
    await act(async () => finish(RESULT));
    expect(await screen.findByRole("dialog", { name: /review your dictation/i })).toBeInTheDocument();
    expect(screen.queryByTestId("processing-indicator")).toBeNull();
  });

  it("uploads the recording with the language and tidy-up preference", async () => {
    const { user } = await setup();
    await record(user, 2500);
    await screen.findByRole("dialog", { name: /review your dictation/i });
    expect(m.submitVoice).toHaveBeenCalledTimes(1);
    const [blob, opts] = m.submitVoice.mock.calls[0];
    expect(blob.size).toBeGreaterThan(800);
    expect(opts).toEqual({ language: "auto", cleanup: true, durationMs: 2500 });
  });

  it("does not ask for tidy-up when the server has no language model", async () => {
    const { user } = await setup(<Harness />, { cleanup_available: false });
    await record(user);
    await screen.findByRole("dialog", { name: /review your dictation/i });
    expect(m.submitVoice.mock.calls[0][1].cleanup).toBe(false);
  });

  it("stops by itself at the server's time limit", async () => {
    const { user } = await setup(<Harness />, { max_seconds: 5 });
    await user.click(mic());
    await screen.findByRole("button", { name: "Stop and transcribe" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Stop and transcribe" })).toBeEnabled());
    now += 6000;
    expect(await screen.findByRole("dialog", { name: /review your dictation/i }, { timeout: 3000 })).toBeInTheDocument();
  });
});

describe("cancelling", () => {
  it("cancel while recording discards everything: no upload, microphone released, field unchanged", async () => {
    const { user, field } = await setup();
    await user.click(mic());
    await user.click(await screen.findByRole("button", { name: "Cancel and discard recording" }));
    expect(screen.queryByTestId("recording-indicator")).toBeNull();
    expect(m.submitVoice).not.toHaveBeenCalled();
    expect(tracks[0].stop).toHaveBeenCalled();
    expect(field().value).toBe("Hello world");
    expect(mic()).toBeInTheDocument();
  });

  it("Escape cancels a recording", async () => {
    const { user } = await setup();
    await user.click(mic());
    await screen.findByTestId("recording-indicator");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByTestId("recording-indicator")).toBeNull());
    expect(m.submitVoice).not.toHaveBeenCalled();
  });

  it("cancelling during the permission prompt releases the stream that arrives late", async () => {
    let grant!: () => void;
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: () => new Promise((r) => { grant = () => r({ getTracks: () => tracks }); }) } });
    const { user } = await setup();
    await user.click(mic());
    await user.click(await screen.findByRole("button", { name: "Cancel and discard recording" }));
    await act(async () => grant());
    expect(tracks[0].stop).toHaveBeenCalled();
    expect(screen.queryByTestId("recording-indicator")).toBeNull();
    expect(recorder).toBeNull();
  });

  it("cancel while transcribing asks the server to drop it and ignores a late result", async () => {
    let finish!: (r: V.VoiceResult) => void;
    m.waitForVoice.mockImplementation(() => new Promise((r) => { finish = r; }));
    const { user, field } = await setup();
    await record(user);
    await user.click(await screen.findByRole("button", { name: "Cancel transcription" }));
    expect(m.discardVoice).toHaveBeenCalledWith("v1");
    await act(async () => finish(RESULT));
    expect(screen.queryByRole("dialog", { name: /review your dictation/i })).toBeNull();
    expect(field().value).toBe("Hello world");
  });

  it("unmounting mid-recording releases the microphone", async () => {
    const { user, view } = await setup();
    await user.click(mic());
    await screen.findByTestId("recording-indicator");
    view.unmount();
    expect(tracks[0].stop).toHaveBeenCalled();
  });
});

describe("failures never lose the user's text", () => {
  it("an empty recording is reported without uploading", async () => {
    const { user, field } = await setup();
    await record(user, 100);
    expect(await screen.findByRole("alert")).toHaveTextContent(/recording was empty/i);
    expect(m.submitVoice).not.toHaveBeenCalled();
    expect(field().value).toBe("Hello world");
  });

  it("a tiny file counts as empty even if the timer says otherwise", async () => {
    const { user } = await setup();
    await user.click(mic());
    const stop = await screen.findByRole("button", { name: "Stop and transcribe" });
    await waitFor(() => expect(stop).toBeEnabled());
    recorder!.bytes = 50; now += 3000;
    await user.click(stop);
    expect(await screen.findByRole("alert")).toHaveTextContent(/empty/i);
    expect(m.submitVoice).not.toHaveBeenCalled();
  });

  it.each([
    [new ApiError(415, "unsupported_format", "This audio format is not supported."), /not supported/],
    [new ApiError(413, "too_large", "Recording is too large."), /too large/],
    [new ApiError(429, "rate_limited", "Dictation limit reached."), /limit reached/],
    [new ApiError(503, "voice_disabled", "Voice input is not set up on this server."), /not set up/],
  ])("shows the server's reason when the upload is refused (%#)", async (error, text) => {
    m.submitVoice.mockRejectedValue(error);
    const { user, field } = await setup();
    await record(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(field().value).toBe("Hello world");
    expect(screen.queryByRole("dialog", { name: /review your dictation/i })).toBeNull();
  });

  it("shows the provider's failure message", async () => {
    m.waitForVoice.mockResolvedValue({ ...RESULT, status: "failed", text: null, error_code: "provider_error", error_message: "The speech service failed (HTTP 500)." });
    const { user, field } = await setup();
    await record(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(/speech service failed/i);
    expect(field().value).toBe("Hello world");
  });

  it("reports silence", async () => {
    m.waitForVoice.mockResolvedValue({ ...RESULT, status: "failed", text: null, error_code: "no_speech", error_message: "No speech was detected." });
    const { user } = await setup();
    await record(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(/no speech was detected/i);
  });

  it("times out politely and cleans up the server copy", async () => {
    m.waitForVoice.mockRejectedValue(new V.VoiceTimeout("t"));
    const { user, field } = await setup();
    await record(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(/taking too long/i);
    expect(m.discardVoice).toHaveBeenCalledWith("v1");
    expect(field().value).toBe("Hello world");
  });

  it("copes with the network being down", async () => {
    m.submitVoice.mockRejectedValue(new TypeError("Failed to fetch"));
    const { user, field } = await setup();
    await record(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach the server/i);
    expect(field().value).toBe("Hello world");
  });

  it("the error can be dismissed and dictation tried again", async () => {
    m.submitVoice.mockRejectedValueOnce(new TypeError("offline"));
    const { user } = await setup();
    await record(user);
    await user.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).toBeNull();
    await record(user);
    expect(await screen.findByRole("dialog", { name: /review your dictation/i })).toBeInTheDocument();
  });
});

describe("review and insertion", () => {
  const dictate = async (user: ReturnType<typeof userEvent.setup>) => { await record(user); return await screen.findByRole("dialog", { name: /review your dictation/i }); };
  const insertBtn = () => within(dialog()).getByRole("button", { name: "Insert" });

  it("shows the transcript for review and does not touch the field until Insert", async () => {
    const { user, field } = await setup();
    await dictate(user);
    expect(within(dialog()).getByLabelText("Transcript")).toHaveValue("call Rohan at 5 pm");
    expect(field().value).toBe("Hello world");
  });

  it("inserts at the cursor without removing anything", async () => {
    const { user, field } = await setup();
    field().setSelectionRange(5, 5);
    await dictate(user);
    await user.click(insertBtn());
    expect(field().value).toBe("Hello call Rohan at 5 pm world");
    expect(screen.queryByRole("dialog", { name: /review your dictation/i })).toBeNull();
  });

  it("keeps a selected passage instead of replacing it", async () => {
    const { user, field } = await setup();
    field().setSelectionRange(6, 11);
    await dictate(user);
    await user.click(insertBtn());
    expect(field().value).toBe("Hello world call Rohan at 5 pm");
  });

  it("can append to the end instead", async () => {
    const { user, field } = await setup();
    field().setSelectionRange(0, 0);
    await dictate(user);
    await user.click(within(dialog()).getByLabelText("Add to the end"));
    await user.click(insertBtn());
    expect(field().value).toBe("Hello world call Rohan at 5 pm");
  });

  it("works in an empty field", async () => {
    const { user, field } = await setup(<Harness initial="" />);
    await dictate(user);
    await user.click(insertBtn());
    expect(field().value).toBe("call Rohan at 5 pm");
  });

  it("lets the user edit the transcript before inserting", async () => {
    const { user, field } = await setup();
    field().setSelectionRange(11, 11);
    await dictate(user);
    const area = within(dialog()).getByLabelText("Transcript");
    await user.clear(area); await user.type(area, "call Priya at 6 pm");
    await user.click(insertBtn());
    expect(field().value).toBe("Hello world call Priya at 6 pm");
  });

  it("will not insert an empty transcript", async () => {
    const { user } = await setup();
    await dictate(user);
    await user.clear(within(dialog()).getByLabelText("Transcript"));
    expect(insertBtn()).toBeDisabled();
  });

  it("Discard changes nothing and tells the server to forget the dictation", async () => {
    const { user, field } = await setup();
    await dictate(user);
    await user.click(within(dialog()).getByRole("button", { name: "Discard" }));
    expect(field().value).toBe("Hello world");
    expect(m.discardVoice).toHaveBeenCalledWith("v1");
    expect(screen.queryByRole("dialog", { name: /review your dictation/i })).toBeNull();
  });

  it("Escape discards the review", async () => {
    const { user, field } = await setup();
    await dictate(user);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: /review your dictation/i })).toBeNull();
    expect(field().value).toBe("Hello world");
  });

  it("collapses line breaks for single-line fields", async () => {
    m.waitForVoice.mockResolvedValue({ ...RESULT, text: "line one\nline two", raw_text: "line one\nline two" });
    const { user, field } = await setup(<Harness single initial="" />);
    await dictate(user);
    await user.click(insertBtn());
    expect(field().value).toBe("line one line two");
  });

  it("focuses the transcript for keyboard users and traps Tab inside the dialog", async () => {
    const { user } = await setup();
    await dictate(user);
    expect(within(dialog()).getByLabelText("Transcript")).toHaveFocus();
    for (let i = 0; i < 8; i++) await user.tab();
    expect(dialog().contains(document.activeElement)).toBe(true);
  });

  it("returns focus to the field after inserting", async () => {
    const { user, field } = await setup();
    await dictate(user);
    await user.click(insertBtn());
    await waitFor(() => expect(field()).toHaveFocus());
  });

  describe("tidied up text", () => {
    const tidy = { ...RESULT, text: "Call Rohan at 5 pm.", raw_text: "um call Rohan at 5 pm", cleaned: true, cleanup_requested: true };

    it("offers the tidied version first and the original on request", async () => {
      m.waitForVoice.mockResolvedValue(tidy);
      const { user } = await setup();
      await dictate(user);
      expect(within(dialog()).getByLabelText("Transcript")).toHaveValue("Call Rohan at 5 pm.");
      expect(within(dialog()).getByText(/numbers, links, emails and names were checked/i)).toBeInTheDocument();
      await user.click(within(dialog()).getByRole("radio", { name: "Original" }));
      expect(within(dialog()).getByLabelText("Transcript")).toHaveValue("um call Rohan at 5 pm");
    });

    it("keeps edits to each version when switching back and forth", async () => {
      m.waitForVoice.mockResolvedValue(tidy);
      const { user } = await setup();
      await dictate(user);
      const area = () => within(dialog()).getByLabelText("Transcript");
      await user.type(area(), " Thanks.");
      await user.click(within(dialog()).getByRole("radio", { name: "Original" }));
      await user.click(within(dialog()).getByRole("radio", { name: "Tidied up" }));
      expect(area()).toHaveValue("Call Rohan at 5 pm. Thanks.");
    });

    it("inserts whichever version is selected", async () => {
      m.waitForVoice.mockResolvedValue(tidy);
      const { user, field } = await setup(<Harness initial="" />);
      await dictate(user);
      await user.click(within(dialog()).getByRole("radio", { name: "Original" }));
      await user.click(insertBtn());
      expect(field().value).toBe("um call Rohan at 5 pm");
    });

    it("explains why cleanup was skipped", async () => {
      m.waitForVoice.mockResolvedValue({ ...RESULT, cleanup_requested: true, note: "Cleanup was not applied (cleanup changed a number, link or email address), so this is the original." });
      const { user } = await setup();
      await dictate(user);
      expect(screen.getByTestId("voice-note")).toHaveTextContent(/not applied/i);
      expect(screen.queryByRole("radio", { name: "Original" })).toBeNull();
    });
  });

  it("states whether audio stayed on the server or went to a cloud service", async () => {
    const local = await setup(<Harness />, { processing: "local" });
    await dictate(local.user);
    expect(within(dialog()).getByText(/processed on your own server/i)).toBeInTheDocument();
    local.view.unmount();
    resetVoiceCaches();
    const cloud = await setup(<Harness />, { processing: "cloud" });
    await dictate(cloud.user);
    expect(within(dialog()).getByText(/sent to an external speech service and deleted/i)).toBeInTheDocument();
  });
});

describe("dictation never acts on its own", () => {
  it("no step of the flow submits the surrounding form", async () => {
    const onSubmit = vi.fn();
    const { user } = await setup(<Harness onSubmit={onSubmit} />);
    await record(user);
    await screen.findByRole("dialog", { name: /review your dictation/i });
    await user.type(within(dialog()).getByLabelText("Transcript"), "{Enter}");
    await user.click(within(dialog()).getByRole("button", { name: "Insert" }));
    await user.click(mic());
    await user.click(await screen.findByRole("button", { name: "Cancel and discard recording" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("language", () => {
  it("uses the language chosen in the settings menu and remembers it", async () => {
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: "Dictation settings for offer" }));
    await user.selectOptions(within(screen.getByRole("dialog", { name: "Dictation settings" })).getByLabelText("Language"), "hinglish");
    expect(JSON.parse(localStorage.getItem("flowhq-voice-prefs")!).language).toBe("hinglish");
    await user.keyboard("{Escape}");
    await record(user);
    await screen.findByRole("dialog", { name: /review your dictation/i });
    expect(m.submitVoice.mock.calls[0][1].language).toBe("hinglish");
  });

  it("tidy-up can be switched off", async () => {
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: "Dictation settings for offer" }));
    await user.click(within(screen.getByRole("dialog", { name: "Dictation settings" })).getByLabelText(/tidy up punctuation/i));
    await user.keyboard("{Escape}");
    await record(user);
    await screen.findByRole("dialog", { name: /review your dictation/i });
    expect(m.submitVoice.mock.calls[0][1].cleanup).toBe(false);
  });

  it("the settings menu says where speech is processed", async () => {
    const { user } = await setup(<Harness />, { processing: "cloud" });
    await user.click(screen.getByRole("button", { name: "Dictation settings for offer" }));
    expect(within(screen.getByRole("dialog", { name: "Dictation settings" })).getByText(/external speech service/i)).toBeInTheDocument();
  });

  it("falls back gracefully if the status request fails", async () => {
    const { user } = await setup(<Harness />, null);
    await user.click(mic());
    expect(await screen.findByTestId("recording-indicator")).toBeInTheDocument();
  });
});

describe("accessibility", () => {
  it("names the field by its label alone, not by the microphone buttons inside the same box", async () => {
    function Labelled() {
      const [v, setV] = useState("");
      return <DictatedField label="Offer" speak="offer" hint="Goes into every message." value={v} onChange={setV}><textarea value={v} onChange={(e) => setV(e.target.value)} /></DictatedField>;
    }
    await setup(<Labelled />);
    const field = screen.getByRole("textbox", { name: "Offer" });                     // exact: no "Dictate offer" or "Dictation settings" folded in
    expect(field).toHaveAccessibleDescription("Goes into every message.");
    expect(screen.getByRole("button", { name: "Dictate offer" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dictation settings for offer" })).toBeInTheDocument();
  });

  it("announces state changes politely for screen readers", async () => {
    const { user } = await setup();
    await user.click(mic());
    await screen.findByTestId("recording-indicator");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/recording offer/i));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/cancelled/i));
  });
});
