# Add Studio Buddy native music companion MVP

Builds a Python/PySide6 companion from the initial README-only repository. Users can
chat with OpenAI Responses, resume SQLite projects/sessions, edit explicit musical
memories and goals, and use coaching actions. Text/voice switching supports Piper,
ElevenLabs and Hume with cancellable generation/playback and stale-result protection.
Includes TOML settings, request safeguards, native dictation-compatible input,
optional read-only MCP resources, packaging, Arch/Sway documentation and CI.

Validation: 33 pytest tests pass on Python 3.12 using real offscreen Qt widgets,
isolated SQLite, mocked cloud APIs and a real child-process cancellation check.
Ruff passes; sdist/wheel build succeeds. Rendered 540×680 desktop smoke inspected.
Per-slice RED/GREEN evidence and commits are recorded in docs/development-log.md.
Remote CI has not been observed.

Limitations requiring review: the specified Renoise MCP tool page was blocked by
environment egress policy. The integration supports official Streamable HTTP MCP
resources only; specific ReMCP compatibility, tool-only/SSE/stdio support and song
metadata capabilities are not verified. It never invokes write or Lua tools.
Arch/Sway, PushTalk F9, hardware playback and live paid providers require the smoke
checks in docs/local-verification.md. Cloud voices use configured IDs, buffered
playback, and explicit local/text fallback. Summaries are manually saved; request
limits are not monetary caps. PushTalk source/configuration/services are untouched.
