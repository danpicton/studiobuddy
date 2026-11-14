# Studio Buddy

A native, local-first musical companion for Renoise. Chat about the loop you have,
try one next experiment, remember the good bits, and pick up where you left off.
Python 3.11+, PySide6, SQLite, OpenAI Responses, and Piper / ElevenLabs
speech. Background voice interaction via a dedicated token-aware speech backend;
the native UI remains available for settings, projects, notes and text conversation.
No Renoise editing.

## Install on Arch Linux / Sway

System prerequisites (once, through your normal package manager):

```sh
sudo pacman -S python uv ffmpeg libxkbcommon wayland fontconfig mesa
```

Install the application in your user account, from a checkout or reviewed release:

```sh
git clone https://github.com/danpicton/studiobuddy.git
cd studiobuddy
# Until merged, check out the reviewed feat/studio-buddy-mvp branch.
uv tool install .
studio-buddy --mock
```

Ensure `~/.local/bin` is on your PATH (`uv tool update-shell` can help).
`--mock` exercises the actual desktop UI with deterministic local replies; ordinary
launch uses OpenAI. A mock reply is not a live AI verification.
To update after pulling changes: `uv tool install --reinstall .`.
When updating an existing development environment from the full Qt bundle, run
`uv sync --locked --reinstall-package pyside6-essentials` once to restore shared
PySide6 files removed by uninstalling the old bundle.
For a desktop launcher, copy `packaging/studio-buddy.desktop` into
`~/.local/share/applications/` and ensure the Sway session PATH includes `~/.local/bin`.
Normal operation requires no root privileges or Docker. No Codex CLI is required.

Development in Codex Web: `uv sync --locked`, then `uv run studio-buddy --mock`.
The environment needs a desktop for interactive use; offscreen Qt is sufficient
for automated tests. See [development evidence](docs/development-log.md).

## First conversation

Run `uv run studio-buddy` from the checkout (or `studio-buddy` after tool installation).
ChatGPT subscription mode is the default, including when loading an older config.

Click **Continue with ChatGPT**, finish sign-in in your system browser, and approve
ChatGPT plan usage for Studio Buddy. Return to the app and choose an available model.
**Refresh models** reloads your account's catalogue; **Manage usage** opens ChatGPT's
usage settings. Your account must be eligible for this preview and grant plan usage.
The app does not use your Codex login or require an API key for subscription replies.
See [OpenAI's local-app integration guide](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt).

**Sign out** revokes the renewable session and clears local tokens. If revocation
cannot be confirmed, the app tells you to disconnect it in ChatGPT Settings → Usage.
This personal desktop implementation keeps one account registration; reauthorization
uses that same account. It does not offer multiple-account switching.

For explicitly separate API billing, select **Ai mode: api** in Settings and set
`OPENAI_API_KEY` securely in the launch environment. The **API model** field applies
only to that mode. ChatGPT mode never falls back to API billing. Cloud speech providers
remain separate paid services; Piper runs locally.

In API mode, reasoning effort sits beside the model: `default` omits the API
parameter; other choices are `none`, `minimal`, `low`, `medium`, `high`, `xhigh`.
Support depends on the model. GPT-4.1 models should use `default`. Reasoning uses
output tokens too; increase the output budget or lower effort if no text is returned.
The subscription adapter currently uses its model default reasoning.

For automatic deeper thinking, save separate **Fast** and **Thinking** models
in the ChatGPT account panel. In API mode, configure **API fast model** and
**API thinking model** in Settings, each with its own reasoning effort. Choose
models appropriate to your account and task; Studio Buddy does not rank them.
Existing model selections remain your fast choices. Thinking starts unconfigured.
Every message starts with the fast model. It answers ordinary conversation itself
and can hand off complex questions to the thinking model. The thinking model gets
the same conversation, memory and one-request Renoise snapshot and supplies the
final answer directly. Only that final answer is stored or spoken; there is no
manual Think checkbox. Status changes to **Thinking more deeply…** on handoff.
The next message starts with the fast model again. Voice and coaching requests
use the same flow. With no thinking model configured, fast chat works normally.

A handoff makes two model requests, both counted against the shared, persisted
session request budget; no thinking call starts if the budget is exhausted.
Displayed token usage combines both calls. Handoff happens at most once per
message, stays in the selected billing mode, and stops on errors or cancellation.
Model judgment determines escalation and can be imperfect. Thinking may consume
more usage and take longer; API output limits also cover reasoning tokens.

Type or paste into the message field and click Send or press **Ctrl+Enter**.
Enter alone adds a newline. Replies stay short and suggest one experiment; the user
judges taste. Voice transcripts follow the same conversation and memory path.

Create/select projects and sessions at the top; edit the current goal beneath them.
**I'm stuck** and **Another idea** request a next experiment. **Remember this** saves
an explicitly confirmed note. **Notes** lets you categorize, edit and delete likes,
experiments, rejections, outcomes, decisions and ideas to revisit. **Wrap up** saves
a short manually edited summary and next step. No paid automatic summary request.
Recent conversation, explicit notes and previous summaries accompany future replies.
All messages remain in SQLite; only the latest 20 messages (4,000 characters each)
and bounded context are sent. Selected Renoise observations reserve space within the
12,000-character context budget before stored memories are trimmed. Old chat is not
automatically promoted into memory.

Default safeguards: 100 requests per session and a 300-token response length setting,
editable in Settings. ChatGPT mode uses that length as a prompt target because its
preview API does not support an enforced output-token limit. API mode sends the limit. Request attempts persist across restart and count failures and
cancellations. API mode can retry once; ChatGPT mode does not automatically retry inference. These
are **not exact spending caps**. Review ChatGPT app usage/credit limits under Manage
usage, or API billing budgets for API mode. Cancellation cannot reverse consumed usage.
Token usage is shown after a reply. Missing keys, auth failures, quotas and network
errors leave history intact and display a safe message; send again when resolved.

## Speech

Text mode never synthesizes replies. Voice mode also displays the text. **Stop /
cancel**, a new message, session change or Text mode interrupts playback and pending
generation. Providers can change in Settings without restarting. **Apply and Test
Voice** explicitly tests the selected provider, including while normal mode is Text.
The button saves those settings. Cloud voice tests may incur charges.

Speech providers share cancellation and bounded audio buffering (20 MB cloud limit).
Playback begins after generation completes; this release does not play partial audio
chunks. Assistant text is sent externally only when the selected cloud provider is
used. Fallback is explicitly **text** (default) or **local Piper**; there is no automatic
switch to another cloud provider. A speech failure never removes the text reply.

### Piper (preferred local voice)

Piper is included in the normal project install (`uv sync` for development or
`uv tool install --reinstall .` for the installed app). Studio Buddy runs it using
its own Python environment, so no separate Piper CLI installation is needed.

Choose/download a voice yourself; models can be large and have their own licences.
Studio Buddy never downloads one automatically. Official instructions:
<https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md>.
Keep the `.onnx` and matching `.onnx.json` together. In Settings choose **piper**,
then **Choose installed Piper .onnx voice**. Test Voice checks generation and ffplay
output. `ffplay` (from the system ffmpeg package) must be on PATH. Playback uses your
normal audio output.
Missing executable, model or model configuration produces a visible error.

### ElevenLabs

Set `ELEVENLABS_API_KEY` securely in the launch environment. Select **elevenlabs**;
copy an available voice ID from your ElevenLabs voice library into **Eleven voice**.
The model defaults to `eleven_multilingual_v2`; stability is configurable from 0 to 1.
Uses the official `/v1/text-to-speech/{voice_id}` endpoint and MP3 audio.

Rejected requests show the HTTP status and ElevenLabs error code in the UI.
Warning logs include the selected voice ID, model ID, stability, HTTP status,
error code and request ID (when supplied). Connection failures log the exception
type. Logs go to stderr by default: launch from a terminal, or for the supplied
background service use:

```sh
journalctl --user -u studio-buddy.service -f
```

Use **Test Voice** to reproduce the failure (this makes a paid API request and
plays audio). A valid key can still lack voice/model access or available credits;
use the returned code to distinguish these from invalid settings. See ElevenLabs'
[error reference](https://elevenlabs.io/docs/eleven-api/resources/errors).
API keys, spoken text, raw response messages and request headers are excluded from
these diagnostics. Malformed, oversized or unsafe error fields fall back to
`unknown`; the HTTP status is still reported. No global HTTP debug logging is needed.

Older configurations with Hume selected open in Text mode with Piper selected.
Obsolete Hume settings are discarded on the next settings save; other preferences
are preserved. Choose Piper or ElevenLabs to enable voice replies again.

## Background voice on F10 (recommended)

Studio Buddy uses a separate capture backend with the same faster-whisper /
CTranslate2 / sounddevice stack as [PushTalk](https://github.com/danpicton/pushtalk).
PushTalk source, configuration, `sttd.service` and F9 remain untouched. Studio Buddy
owns its private capture socket and carries a recording token alongside the audio
through transcription and GUI submission. It does not infer recording identity from
an `idle` status or use PushTalk's shared `--type-cmd` callback.

The supplied service keeps a CPU int8 `small.en` model warm, uses four threads to
leave room for music, and captures with no pre-roll. Change model/device/language
options in the Studio Buddy service only; for other languages use a multilingual
model and `--language auto`. Both backends share Hugging Face's downloaded model
cache but load separate models in RAM and open separate mic streams. Check that
PipeWire allows both. Install PortAudio on Arch (`portaudio`) and Studio Buddy's
optional speech dependencies; ordinary UI installations do not load these libraries.

First open the UI, select your project/session, configure your model and a working
Piper voice (or chosen cloud voice), and use Test Voice. Then close the regular app
and install the supplied units:

```sh
uv tool install --reinstall ".[speech,renoise]"
mkdir -p ~/.config/systemd/user
cp packaging/studio-buddy*.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

For ChatGPT mode, sign in and choose a model in the UI first; the background app
uses the same saved account. For API mode, arrange for `studio-buddy.service` to
receive `OPENAI_API_KEY` through your secure session/credential mechanism. Keys
exported in an ordinary shell are not automatically inherited by systemd.
Add [packaging/studio-buddy.sway](packaging/studio-buddy.sway) to your Sway config
and reload Sway, or start the units after importing the session environment:

```sh
systemctl --user import-environment WAYLAND_DISPLAY XDG_CURRENT_DESKTOP SWAYSOCK
systemctl --user start studio-buddy.service studio-buddy-stt.service studio-buddy-voice.service
```

Bindings provided for you to merge yourself:

```sway
bindsym --no-repeat F10 nop studio-buddy:start
bindsym --release F10 nop studio-buddy:stop
bindsym $mod+F10 exec studio-buddy-voice show
bindsym $mod+Shift+F10 nop studio-buddy:cancel
```

**Existing installations must reinstall with the speech extra, replace the supplied
`studio-buddy-stt.service`, and restart all three Studio Buddy services.** The old
unit's untagged PushTalk callbacks are deliberately rejected. Replace old
`exec … start/stop` bindings with these `nop` bindings and install/start
`studio-buddy-voice.service`. Standalone
`studio-buddy-voice start` now refuses capture: independently spawned commands
cannot reliably preserve the order of a press and release. The persistent listener
reads Sway's ordered binding events, records each intent before dispatching work,
and cancels on startup, disconnect and shutdown. After a service restart/reconnect,
release F10 and press again; a key already held is never inferred as a new press.
After updating units, restart them:

```sh
systemctl --user restart studio-buddy.service studio-buddy-stt.service studio-buddy-voice.service
```

If the listener is unavailable, F10 does nothing. `stop` and `cancel` remain usable
from a terminal for recovery. Only the supplied exact `nop studio-buddy:…` commands
are recognized; do not add other commands to the same binding.

Hold F10, speak, release: the transcript is submitted automatically to the current
session and the reply is spoken. Starting a recording interrupts Buddy's pending
reply/playback. A new press supersedes any older recording or transcript. The model
runs one inference at a time; at most one newer completed recording waits for it.
Cancellation discards captured/queued audio and rejects late output; an inference
already running may finish in the background. A missed release is bounded by a
120-second sample cap in the audio callback, which seals audio and its identity
together and may transcribe that recording. An observed listener failure cancels
and rejects its transcript instead. Changing sessions, sending text or cancelling
invalidates the pending transcript. Unsaved editor text remains intact.
Do not change projects while dictating; select the intended project first in the UI.

`studio-buddy --background` starts hidden and uses the saved Text/Voice mode with
the saved provider. Normal launch shows the UI; launching again shows the existing
instance. Closing the background window hides it and keeps the companion running.
Left-click the tray icon to start recording, then click again to send it for
transcription and a reply (spoken when Voice replies is enabled). The icon turns pink/red while starting/recording
and returns to purple when stopped. Double-click is ignored to avoid an extra
recording toggle. Right-click for Show Studio Buddy, Hide window, Cancel voice or
Quit. Tray recording needs `studio-buddy-stt.service` running; it does not require
the Sway binding listener. The app never starts the microphone service itself.
If the backend is missing, the tooltip/notification tells you to check/start it.
On Sway, enable the `tray` module in Waybar (or another StatusNotifier host).
Without a tray host, the show binding and CLI remain available.
`studio-buddy-voice show` / `hide` control the window; `cancel` interrupts both capture
and the response. Desktop notifications show response/error status (requires
`notify-send` and a notification daemon). One notification updates in place using
the daemon's returned ID. Rapid updates queue in order, each for at least one
second after delivery; consecutive duplicates are skipped. Updates request a
1.8-second expiry, so the final status disappears automatically when the daemon
honours the timeout. Mako can override this with a Studio Buddy-specific rule.
Display timing does not delay capture, inference or playback. If notify-send fails
or returns an invalid ID, popups stop for that app launch to avoid stacking;
status and conversation text remain available in the UI.
To stop the background services:

```sh
systemctl --user stop studio-buddy-voice.service studio-buddy-stt.service studio-buddy.service
```

`studio-buddy-voice quit` exits the app; systemd also stops its dependent STT and voice-listener units.
You can still focus the editor and use existing F9 dictation, inspect it and submit
with Ctrl+Enter. Studio Buddy does not install bindings or start microphone capture
itself: you explicitly start its separate speech service. The backend keeps its mic
stream open while the service runs; it retains audio only while F10 recording is
active, with no idle pre-roll. Backend logs omit audio and transcript content.
Check services and errors:

```sh
systemctl --user status studio-buddy-stt.service studio-buddy-voice.service
journalctl --user -u studio-buddy.service -u studio-buddy-stt.service -u studio-buddy-voice.service
```

Model loading must finish before F10 can start a capture. On failure, release and
press again once the backend is ready. Backend/listener restart revokes old intent;
late jobs cannot be relabelled as a new recording. Shutdown closes the mic and
revokes acceptance; systemd enforces a ten-second stop deadline for native code.

## Optional Renoise context

[ReMCP by kunitoki](https://www.renoise.com/tools/renoise-mcp) exposes song data
through MCP tools. Studio Buddy supports five fixed, argument-free reads:
`song_get_info`, `tracks_list`, `patterns_list`, `instruments_list`, and
`sequencer_list`. Write tools and arbitrary Lua execution are never available to
the AI. Servers advertising MCP resources continue to use the resource interface.

For checkout development with voice support:

```bash
uv sync --extra speech --extra renoise
uv run --extra speech --extra renoise studio-buddy
```

For the separate installed command, use
`uv tool install --reinstall '.[speech,renoise]'`, then restart the app.
Renoise support is optional; the default installation omits MCP dependencies.

Start the server in Renoise via Tools → Renoise MCP. Enable MCP in Studio Buddy
Settings, use ReMCP's default `http://localhost:19714/mcp` (or your configured
endpoint), Save, then Connect. Select an observation and click **Read once**.
Up to 8,000 text characters become untrusted context for the next AI request only.
Refresh explicitly when the song changes. There is no background polling or AI
access to tools. Only literal loopback/localhost HTTP endpoints are accepted,
without credentials, queries or redirects. SSE and stdio are unsupported.
Disconnected MCP leaves chat usable.

Mocked tests cover capability selection and the read-only allowlist. Live ReMCP
compatibility on Arch/Sway still requires a manual Connect → Read once → chat check
with Renoise and a song loaded; no paid API call is needed to test Connect/Read once.

## Local files, privacy and backup

- Settings: `$XDG_CONFIG_HOME/studio-buddy/config.toml` (default `~/.config/...`).
- Database: `$XDG_DATA_HOME/studio-buddy/memory.sqlite` (default `~/.local/share/...`).
- Audio: private temporary directories, deleted after playback/cancellation.
- ChatGPT credentials: `$XDG_CONFIG_HOME/studio-buddy/chatgpt-auth.json`, atomically
  written with mode 0600. Contains OAuth tokens; never share or commit this file.
- API/voice keys: process environment only. No credentials enter settings, DB or logs.

Settings and database files are mode 0600. Data is local, not encrypted; protect your
user account and disk. Chat and selected context go to OpenAI (`store=false`); cloud
speech sends reply text to the explicitly selected provider. Provider retention terms
still apply. To back up, close the app and copy the data directory and config file.
The `.xrns` path is a reference only: this app never opens it for writing.
`config.example.toml` contains every supported setting and no secrets.

## Tests and verification

```sh
uv sync --locked
QT_QPA_PLATFORM=offscreen uv run pytest -q
uv run ruff check src tests
uv build
```

Tests use native Qt widgets, isolated databases, fake providers and HTTP transports;
no real credentials, mic, Renoise or audio hardware required. OAuth tests use a
loopback callback and generated test signing keys; remote endpoints are mocked. CI runs Python 3.11 and
3.12. Tests verify actual widget conversations, persistence, cancellation/stale results,
request payloads/errors, notes/settings and MCP resource restrictions. See
[local verification checklist](docs/local-verification.md) for checks that cannot be
claimed from mocks, and [API references](docs/integrations.md) for sources.

## Troubleshooting

- No reply: in ChatGPT mode, sign in, choose a listed model and check Manage usage.
  In API mode, check key presence and billing. Both modes need network/model access
  and remaining session requests.
- No speech: check Text/Voice, selected voice/model, ffplay/Piper PATH and audio output.
  Cloud auth/quota errors appear without remote response bodies or keys.
- Qt cannot load Wayland: verify Arch prerequisites and run in the actual Sway session;
  `offscreen` is for CI, not normal use. Do not set it in your desktop launcher.
- Invalid TOML: repair config using the example. Keep a backup; the app does not
  silently overwrite malformed settings. SQLite corruption requires restoring backup.
- MCP unavailable: confirm protocol/resource support and endpoint; ordinary chat works.
- Voice unavailable: check both Studio Buddy services, the selected voice, and
  `XDG_RUNTIME_DIR`. Keep the directory private (0700). Existing F9 needs no changes.

Known limitations: Arch/Sway, microphone capture, actual speech output, paid provider calls, F9/F10
and the specified Renoise tool remain live smoke tests. No cloud voice catalogue,
partial-audio playback, automatic summarization or hard currency spending cap.
