# Add Studio Buddy desktop companion with voice and read-only Renoise context

Adds a native PySide6 music companion with project/session history, editable
memories and creative goals in SQLite. Supports ChatGPT subscription sign-in
and explicitly selected OpenAI API billing, with request limits and protected
local credential storage.

- Background tray recording and optional F10 controls use a dedicated, token-aware
  speech backend. Cancellation rejects stale transcripts/replies across sessions.
  PushTalk and F9 remain independent.
- Piper installs with the app; ElevenLabs is the supported cloud voice provider.
  Hume support is removed with migration of old configurations. Background startup
  respects the saved Text/Voice mode. Status notifications replace one popup and
  routine recording preparation no longer reports a false interruption.
- Optional local MCP context supports advertised resources or five fixed read-only
  ReMCP observations. Connect discovers entries; Read once attaches a bounded
  snapshot to the next message. The model receives no arbitrary or write tools.

Includes Arch/Sway installation and service examples, an offscreen CI matrix,
manual verification instructions and per-slice development evidence. Downloaded
local Piper voices are ignored rather than distributed with the source.

Validation: `QT_QPA_PLATFORM=offscreen uv run pytest` passed 161 tests;
`uv run ruff check` and `git diff --check` passed. Tests use mocked cloud and
capture services, real offscreen Qt widgets and bounded local IPC/process checks.

Manual checks remain for live ReMCP Connect → Read once → chat, account/provider
access, paid API calls, hardware audio and Arch/Sway session behavior. Mocked
coverage does not establish those integrations; see docs/local-verification.md.
