# Studio Buddy

A native, local-first musical companion for Renoise. Chat about the loop you have,
try one next experiment, remember the good bits, and pick up where you left off.
Python 3.11+, PySide6, SQLite, OpenAI Responses, and optional Piper / ElevenLabs /
Hume speech. No browser UI, microphone service, audio listening or Renoise editing.

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

Type or paste into the message field and click Send or press **Ctrl+Enter**.
Enter alone adds a newline. Replies stay short and suggest one experiment; the user
judges taste. Studio Buddy never hears your audio.

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

## PushTalk stays independent

Focus the Studio Buddy message field, hold your **existing F9** binding, speak,
release, inspect the transcribed text, then Send / Ctrl+Enter. PushTalk's `wtype`
output goes into the native focused editor. Studio Buddy does not install or change
PushTalk, its configuration, its daemon, or its bindings, and does not capture a mic.
Typing and pasting work without PushTalk. Actual wtype/F9 injection needs Sway testing.

Optional Sway snippets, to add yourself if desired (choose unused bindings):

```sway
bindsym $mod+Shift+b exec studio-buddy
bindsym $mod+b [app_id="studio-buddy"] focus
bindsym $mod+Ctrl+b [app_id="studio-buddy"] move scratchpad
bindsym $mod+Mod1+b [app_id="studio-buddy"] scratchpad show
```

Launch once before using focus/show. These never use F9. The window is not always
on top and uses no X11 window-management calls. Qt uses Wayland in a normal Sway
session; if needed launch with `QT_QPA_PLATFORM=wayland studio-buddy`.

## Optional Renoise context — compatibility limitation

The requested tool is <https://www.renoise.com/tools/renoise-mcp>. Install it according
to its own documentation. **Compatibility with that specific tool is not yet verified**:
the tool page was blocked by the build environment's network policy. The accessible
`zakhap/renoise-mcp` project documents write/evaluate-Lua tools, which this app refuses
to invoke. Do not assume it is the same project or substitute it for a resource server.

Renoise support is an optional installation extra. From the checkout, run
`uv tool install --reinstall '.[renoise]'` (development: `uv sync --extra renoise`).
The default installation omits MCP and its server/authentication dependencies.

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
- New instance opens instead of showing one: use focus/scratchpad binding after launch;
  this version does not implement a single-instance DBus service.

Known limitations: Arch/Sway, actual speech output, paid provider calls, PushTalk F9
and the specified Renoise tool remain live smoke tests. No cloud voice catalogue,
partial-audio playback, automatic summarization or hard currency spending cap.
