# Vertical-slice development evidence

All automated Qt checks use QT_QPA_PLATFORM=offscreen. Live integrations are separate.

## 1 — Desktop conversation
RED: pytest collection failed: studiobuddy.app did not exist.
GREEN: native window accepted a message, background mock replied, history rendered; 1 passed.
REFACTOR: isolated cancellable asyncio runner from widgets; regression 1 passed.

## 2 — OpenAI Responses
RED: test_ai could not import OpenAIBackend. GREEN: 4 tests passed including
request/output limits, safe errors and missing credentials. Official openai-python
README consulted; requests use Responses, store=false, bounded input, timeout/retry.
REFACTOR: formatted; regression 4 passed. Live paid API not exercised.

## 3 — Persistence
RED: missing storage module. GREEN: 6 passed, including window close/reopen,
project isolation, goals and conversation ordering. SQLite transactions, foreign keys,
WAL and private database permissions. REFACTOR: formatted; regression 6 passed.

## 4 — Coaching
RED: missing goal widget and insufficient personality instructions (2 failures).
Initial GREEN run exposed repeated-close teardown errors; made shutdown idempotent.
GREEN: 8 passed after correction. Editable goal persists; personality is a dedicated maintainable
module, separate from untrusted session data. REFACTOR: format; regression 8 passed.

## 5 — Focused dictation-compatible input
RED: Ctrl+Enter submission timed out. Initial QShortcut did not handle the focused
editor reliably in offscreen Qt; moved handling to the editor's key event.
GREEN: 9 passed; REFACTOR: format, regression 9 passed. Native paste is verified;
actual wtype/F9 remains an Arch/Sway smoke test. PushTalk was not modified.

## 6 — Local speech and interruption
RED: speech module absent. GREEN: 12 passed, including text silence and a cancelled
provider deliberately returning stale audio. Generation fencing prevents playback.
Piper CLI follows OHF-Voice/piper1-gpl documentation; ffplay subprocess is killed and
reaped on cancellation. REFACTOR: format; regression 12 passed. Hardware untested.

## 7 — ElevenLabs adapter
RED: providers module missing. GREEN: 14 passed. Mock HTTP verifies endpoint,
voice settings, missing credentials and rate limits. Official elevenlabs-python
reference consulted. Audio is downloaded asynchronously in bounded chunks, then
played; cancellation closes HTTP stream. REFACTOR: shared bounded download helper;
regression 14 passed. Settings wiring follows in packaging/settings slice.

## 8 — Hume adapter
RED: Hume import failed (2 tests). GREEN: 16 passed. Verified distinct /v0/tts/file
payload, voice ID, acting description, WAV format and authentication error handling.
Source: official HumeAI/hume-python-sdk tts/raw_client.py and posted_utterance.py.
REFACTOR: format; regression 16 passed. Live Hume/ElevenLabs calls not made.

## 9 — Project memory and continuity
RED: Store.notes and Window.create_project absent. GREEN: 18 passed. Added project/
session selection, explicit categorized notes (including rejected experiments and
outcomes), edit/delete, manual concise wrap-up/next-step, context across sessions,
and coaching buttons. No automatic promotion of chat to memory. REFACTOR: notes
editor separated from main window, formatting; regression 18 passed.

## 10 — Optional read-only MCP resources
RED: renoise module absent. GREEN: 21 passed: advertised-resource allowlist,
no tool calls, local endpoint restrictions and unavailable connection.
Uses installed official MCP SDK Streamable HTTP resource interface. The requested
renoise.com tool page is blocked by egress policy; a network draft was saved.
GitHub zakhap/renoise-mcp documents write tools / evaluate_lua only; these are
intentionally unsupported. Resource-only adapter is implemented, but compatibility
with the user's ReMCP server and song/note resources remains unverified. No tool
names or data capabilities invented. REFACTOR: format; regression 21 passed.

## 11a — Settings, integration and hardening
RED: settings module absent. Added restart-safe TOML, runtime provider selection,
Test Voice, external-text disclosure, local/text-only fallback and theme/MCP settings.
Additional RED: a supposedly one-request Renoise snapshot leaked into the next
request; now consumed once. Stale-AI cancellation test passed without changes.
GREEN: 26 passed. REFACTOR: formatting/import organization and explicit exception
boundary comments; ruff clean, regression 26 passed. Request counts persist per
session. Secrets are never written to settings. Native packaging/docs next.

## 11b — Packaging and verification
Additional regression checks (passed immediately, not claimed as RED evidence):
real OpenAI SDK with mocked HTTP 401/429 responses, and cancellation of a real
sleeping subprocess with verified child reaping. Full suite: 29 passed on Python 3.12.
ruff check passed. uv build produced sdist and wheel. Offscreen desktop smoke opened
the real 540×680 window, sent/received a message, captured and visually inspected its
rendering, and shut down cleanly. CI matrix for Python 3.11/3.12 is configured but
remote CI has not been observed. Documentation covers install, credential setup,
provider differences, PushTalk independence, Sway and live verification gaps.
GitHub API probe returned Forbidden; native Git publication is tested separately.

## Final regression and publication evidence
33 tests passed after adding checks for voice-failure recovery in the real window,
persistent request limits across restart, and safe timeouts for both cloud voices.
These additional regression tests passed without production changes. Branch
feat/studio-buddy-mvp was successfully pushed using existing platform Git access.
Environment status still reports revision 1 with no custom domains applied; the
saved network draft has not changed runtime access. GitHub API access remains blocked.
Reusable uv install/start instructions were saved in the environment draft.

## Review fix 1 — Minimal Qt dependency
RED: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_dependencies.py -q`
failed as expected: the default dependency closure included Qt Addons, WebEngine
and PDF. The regression checks the resolved installation, not just the direct name.
GREEN / regression: 34 tests passed; `uv run ruff check` passed. Removed the full
Qt metapackage and its Addons/WebEngine/PDF closure. During migration, uninstalling
the metapackage removed a shared PySide6 file; reinstalling Essentials repaired it.
No further refactor was needed. Live Arch/Sway/audio checks remain unrun.

## Review fix 2 — Optional Renoise dependencies
RED: dependency tests produced two expected failures: the default install includes
MCP's server/auth stack, and desktop startup fails when MCP cannot be imported.
GREEN / regression: default install 35 passed, 1 MCP transport test skipped;
Renoise extra installed: 36 passed. Ruff initially caught a missing explicit
subprocess check argument in the new test; fixed and rerun successfully. REFACTOR:
lazy SDK imports stay inside the adapter; safe adapter errors reach the UI.
CI now covers both installation modes. Live Renoise compatibility remains untested.
