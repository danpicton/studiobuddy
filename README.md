# Studio Buddy

A native, local-first musical companion for Renoise. Chat about the loop you have,
try one next experiment, remember the good bits, and pick up where you left off.
Python 3.11+, PySide6, SQLite, OpenAI Responses, and Piper / ElevenLabs / Hume
speech. Background voice interaction via a dedicated, unmodified PushTalk daemon;
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
For a desktop launcher, copy `packaging/studio-buddy.desktop` into
`~/.local/share/applications/` and ensure the Sway session PATH includes `~/.local/bin`.
Normal operation requires no root privileges or Docker. No Codex CLI is required.

Development in Codex Web: `uv sync --locked`, then `uv run studio-buddy --mock`.
The environment needs a desktop for interactive use; offscreen Qt is sufficient
for automated tests. See [development evidence](docs/development-log.md).

## First conversation

Set `OPENAI_API_KEY` securely in the launch environment, then run `studio-buddy`.
Do not commit keys, paste them into chat, or put them in `config.toml`.
For a terminal launch without putting a value in shell history:

```sh
read -rs -p 'OpenAI API key: ' OPENAI_API_KEY; echo
export OPENAI_API_KEY
studio-buddy
```

A desktop launcher must inherit the variable from your session or your own secure
credential launcher. Settings shows only whether a key is present, never its value.
A ChatGPT subscription does **not** include API billing. Configure an OpenAI API
account and billing separately. Default model: `gpt-4.1-mini`, changeable in Settings.
Reasoning effort sits beside the model: `default` omits the API parameter; other
choices are `none`, `minimal`, `low`, `medium`, `high`, `xhigh`. Support depends on
the model. For example, GPT-4.1 models should use `default`; choose a reasoning
model before requesting an explicit effort. Reasoning consumes output tokens too: the
300-token default may produce no visible answer with a reasoning model; increase
the output limit and/or lower effort if needed. Unsupported model/effort combinations
produce a safe request error and can be corrected in Settings.

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
and bounded context are sent. Old chat is not automatically promoted into memory.

Default safeguards: 100 requests per session, 300 output tokens per request;
editable in Settings. Request attempts persist across restart and count failures and
cancellations. The SDK can retry once, so these are **not exact financial caps**.
Set provider-side billing budgets as well. Cancellation cannot reverse API charges.
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

Install the official Piper CLI into an isolated tool environment:

```sh
uv tool install piper-tts
```

Choose/download a voice yourself; models can be large and have their own licences.
Studio Buddy never downloads one automatically. Official instructions:
<https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md>.
Keep the `.onnx` and matching `.onnx.json` together. In Settings choose **piper**,
then **Choose installed Piper .onnx voice**. Test Voice checks generation and ffplay
output. `piper` and `ffplay` must be on PATH. Playback uses your normal audio output.
Missing executable, model or model configuration produces a visible error.

### ElevenLabs

Set `ELEVENLABS_API_KEY` securely in the launch environment. Select **elevenlabs**;
copy an available voice ID from your ElevenLabs voice library into **Eleven voice**.
The model defaults to `eleven_multilingual_v2`; stability is configurable from 0 to 1.
Uses the official `/v1/text-to-speech/{voice_id}` endpoint and MP3 audio.

### Hume

Set `HUME_API_KEY`; choose **hume** and an available voice ID from your Hume Voice
Library. Add a short delivery description (e.g. “Warm and wry”) and speed 0.75–1.5.
Uses the official `/v0/tts/file` API with WAV output and one generation. Hume's
expressive description is distinct from ElevenLabs stability. Voice IDs are entered
manually; this release does not fetch cloud voice catalogues.

## Background voice on F10 (recommended)

Install [PushTalk](https://github.com/danpicton/pushtalk) normally so `sttd` and
`sttctl` are on PATH. No changes to PushTalk source, configuration, `sttd.service`
or F9 are required. We reuse its existing `--socket`, `--state-file` and
`--type-cmd` interfaces in a **second instance**. The existing daemon injects text
with wtype; the Studio Buddy instance sends stdin transcripts to
`studio-buddy-voice submit` through a private local socket. No window focus needed.

Recommended STT matches PushTalk: faster-whisper / CTranslate2, CPU, int8,
`small.en` for English. The supplied service uses four threads to leave room for
music, and zero pre-roll to reduce pickup of Buddy's previous reply. Change these
in the Studio Buddy service only. For other languages use a multilingual model
and `--language auto`. Both instances share Hugging Face's downloaded model cache,
but each loads its own model in RAM and opens its own mic stream. Check PipeWire
allows both. This does not reuse the already-running F9 daemon's in-memory model;
that daemon has no per-request transcript destination API. No backend fork needed.

First open the UI, select your project/session, configure your model and a working
Piper voice (or chosen cloud voice), and use Test Voice. Then close the regular app
and install the supplied units:

```sh
uv tool install --reinstall .
mkdir -p ~/.config/systemd/user
cp packaging/studio-buddy.service packaging/studio-buddy-stt.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

Arrange for `studio-buddy.service` to receive `OPENAI_API_KEY` through your existing
secure session/credential mechanism. The supplied unit contains no credentials;
keys exported in an ordinary shell are not automatically inherited by systemd.
Add [packaging/studio-buddy.sway](packaging/studio-buddy.sway) to your Sway config
and reload Sway, or start the units after importing the session environment:

```sh
systemctl --user import-environment WAYLAND_DISPLAY XDG_CURRENT_DESKTOP SWAYSOCK
systemctl --user start studio-buddy.service studio-buddy-stt.service
```

Bindings provided for you to merge yourself:

```sway
bindsym --no-repeat F10 exec studio-buddy-voice start
bindsym --release F10 exec studio-buddy-voice stop
bindsym $mod+F10 exec studio-buddy-voice show
bindsym $mod+Shift+F10 exec studio-buddy-voice cancel
```

Hold F10, speak, release: the transcript is submitted automatically to the current
session and the reply is spoken. Starting a recording interrupts Buddy's pending
reply/playback. Wait for transcription before recording again; overlapping jobs are
refused. Lost release auto-stops at 120 seconds. Changing sessions, sending text or
cancelling invalidates the pending transcript. Unsaved editor text remains intact.
Do not change projects while dictating; select the intended project first in the UI.

`studio-buddy --background` starts hidden and enables speech for that launch using
the saved provider. Normal launch shows the UI; launching again shows the existing
instance. Closing the background window hides it and keeps the companion running.
`studio-buddy-voice show` / `hide` control the window; `cancel` interrupts both capture
and the response. Desktop notifications show response/error status (requires
`notify-send` and a notification daemon). Conversation text/errors remain in the UI.
To stop both background services:

```sh
systemctl --user stop studio-buddy-stt.service studio-buddy.service
```

`studio-buddy-voice quit` exits the app; systemd also stops its dependent STT unit.
You can still focus the editor and use existing F9 dictation, inspect it and submit
with Ctrl+Enter. Studio Buddy does not install bindings or start microphone capture
itself: capture runs only when you explicitly start its separate PushTalk instance.
PushTalk keeps the mic open while its daemon runs, even between keypresses; it logs
transcript excerpts (and full transcripts on injection failures) to its journal.
Review retention there if conversations are sensitive. Check status with
`sttctl --socket "$XDG_RUNTIME_DIR/studio-buddy/sttd.sock" status` and logs with
`journalctl --user -u studio-buddy.service -u studio-buddy-stt.service`.

## Optional Renoise context — compatibility limitation

The requested tool is <https://www.renoise.com/tools/renoise-mcp>. Install it according
to its own documentation. **Compatibility with that specific tool is not yet verified**:
the tool page was blocked by the build environment's network policy. The accessible
`zakhap/renoise-mcp` project documents write/evaluate-Lua tools, which this app refuses
to invoke. Do not assume it is the same project or substitute it for a resource server.

This release implements the official MCP **Streamable HTTP resource** interface only.
If your server publishes read-only song/note resources, enable MCP in Settings and
enter its documented local HTTP endpoint, then Connect. `http://127.0.0.1:8000/mcp`
is only a configurable example, not a verified ReMCP default. Select one advertised
resource and **Read once**. Up to 8,000 text characters become untrusted, observed
context on the next AI request only. Refresh explicitly when the song changes.
There is no background polling, no full-song upload and no AI tool access.

Only literal loopback/localhost endpoints are accepted, without credentials,
queries or redirects. No MCP tools are listed or called; arbitrary Lua execution is
never allowed. Servers exposing only tools, SSE or stdio are unsupported in v0.1.
No song, track, pattern, arrangement or instrument capabilities are invented.
Disconnected/unsupported MCP leaves ordinary chat fully usable. A verified adapter
for the specific Renoise server remains the principal integration gap.

## Local files, privacy and backup

- Settings: `$XDG_CONFIG_HOME/studio-buddy/config.toml` (default `~/.config/...`).
- Database: `$XDG_DATA_HOME/studio-buddy/memory.sqlite` (default `~/.local/share/...`).
- Audio: private temporary directories, deleted after playback/cancellation.
- Credentials: process environment only; not stored in settings, DB or logs.

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
no paid credentials, mic, Renoise or audio hardware required. CI runs Python 3.11 and
3.12. Tests verify actual widget conversations, persistence, cancellation/stale results,
request payloads/errors, notes/settings and MCP resource restrictions. See
[local verification checklist](docs/local-verification.md) for checks that cannot be
claimed from mocks, and [API references](docs/integrations.md) for sources.

## Troubleshooting

- No reply: check key presence, model access, network, API credits and request limit.
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
