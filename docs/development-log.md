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

## 12 — Model reasoning effort
RED: targeted suite 5 failed / 8 passed: backend/settings rejected reasoning_effort.
Initial uv invocation was blocked by read-only default cache; subsequent commands
use UV_CACHE_DIR=/workspace/work/uv-cache. Added persisted model-specific effort,
Settings selector, runtime application and optional Responses reasoning payload.
GREEN / REFACTOR / regression: ruff format; 38 tests passed; ruff check passed.
Paid model compatibility is a manual check; default omits reasoning for existing models.

## 13 — Background voice entry point
RED: 3 voice behavioural tests failed with missing voice_input module.
Reusing PushTalk main (inspected README, daemon and ctl): separate sttd with its
existing --socket / --state-file / --type-cmd options. No PushTalk modifications
and no microphone capture executed in development. User request supersedes the
old no-microphone product scope; capture remains in the separate PushTalk service.

GREEN: initial voice tests passed; expanded regression 45 passed. ruff identified
three issues (exception type and explicit subprocess check), corrected. Build passed.
Real CLI smoke then found a hidden-launch crash: QLabel has no textChanged signal.
Added StatusLabel signal and a regression test before retrying the process smoke.
Process smoke exposed quit acknowledgement being cut off by shutdown. Flush the
reply and defer quitting until the next Qt turn. Retried from a fresh isolated XDG
state: hidden --mock launch, transcript IPC, SQLite conversation, second-instance
show, hide and quit all passed. No capture or paid calls. Notifications require a
real desktop. Added status-signal and CLI dedicated-socket/ordering regressions.
Final REFACTOR / regression: 47 tests passed; ruff check and git diff --check passed;
uv build produced wheel and sdist. Live Arch/Sway F10/F9 coexistence, PipeWire mic,
CPU contention during music, notification display, actual speech and paid model
reasoning remain explicitly unverified. Service files are supplied, not installed
or started. PushTalk checkout used for inspection only; upstream is unmodified.

## 14 — Serialize voice controls and cancel independently of the GUI
RED: `UV_CACHE_DIR=/workspace/work/uv-cache QT_QPA_PLATFORM=offscreen uv run
pytest tests/test_voice_control.py -q` produced 4 failed / 2 passed. Separate spawned
CLI processes reproduced stop and cancel completing during blocked GUI preparation,
then the stale start turning fake capture on. GUI unavailable/timeout tests reproduced
cancel skipping STT entirely. The two start-GUI-failure guards passed unchanged.

GREEN: original regressions and existing voice tests passed (15 tests). The private
runtime lock file now holds a per-start token. All STT status/start/stop/cancel
commands share its OS file lock across CLI processes. GUI preparation happens
outside the lock: stop/cancel clear the token without waiting for the GUI, and a
stale start exits successfully without starting capture. The final token check and
STT start share the lock, ordering a racing stop/cancel after any already-issued
start. Cancellation attempts STT first and GUI second, including daemon errors.

REFACTOR: formatted the changed Python files and isolated the existing busy-daemon
test's runtime directory. STT command/error handling and lock lifetime use shared
helpers. Expanded regression tests passed immediately (not extra RED
claims): cancel with unavailable/timed-out GUI still invalidates another process's
pending start; stop/cancel serialize behind an in-flight daemon start; failed or
timed-out STT cancellation still attempts GUI cancellation. Services are fakes;
CLI processes, file locking, token storage and synchronization are real.

Regression: `UV_CACHE_DIR=/workspace/work/uv-cache QT_QPA_PLATFORM=offscreen uv run
pytest` passed all 59 tests; `UV_CACHE_DIR=/workspace/work/uv-cache uv run ruff check`
and `git diff --check` passed. Reviewed the complete change. PushTalk code,
configuration, services and F9 bindings remain untouched. No microphone capture or
paid API calls were made. Actual Arch/Sway key delivery, PipeWire capture, daemon
failure recovery and real desktop notification/speech behavior remain manual
hardware checks. A control already inside STT IPC can delay release/cancel until
that bounded subprocess returns (six-second timeout); GUI waiting holds no lock.
