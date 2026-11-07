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

## 15 — Causal Sway events and immediate transcript revocation
RED: `UV_CACHE_DIR=/workspace/work/uv-cache QT_QPA_PLATFORM=offscreen uv run
pytest tests/test_voice_ordering.py -q` failed all 7 tests. The missing event-source
registration/listener API prevents expressing causal key order with the old CLI;
its standalone start also lacks the required fail-closed migration behavior.
Tests cover a child not executing until after source release, late GUI callbacks,
transcript acceptance during recorder cancellation, and stream failure cleanup.
This replaces the insufficient claim in section 14: lock acquisition cannot infer
the order of independently spawned Sway commands.

GREEN: the initial 7 tests passed. Added passing regressions for cross-process
revocation while STT cancellation is gated, GUI timeout independence, duplicate
listeners, fresh-start behavior after stream loss, SIGTERM and stale CLI callback
identity. Migrated the old tests to source-issued identities; independent CLI
`start` deliberately fails closed. The GUI checks recording identity and the existing
window/session token before saving/submitting, under a short nonblocking state lock.

Self-review RED/GREEN: a cleanup-timeout test failed because waiting for swaymsg
could skip final mic cancellation. Cleanup now cancels first and kills/reaps a
non-exiting child; the regression passed. An interrupted-state-write test then
failed with JSONDecodeError after a partial write. State is now atomically replaced
under a separate stable lock, preserving the previous usable state on interruption.

REFACTOR: ruff formatting/import ordering; shared state and control helpers. Added a
persistent listener service with ExecStopPost cancellation for crashes; changed only
Studio Buddy's supplied F10 bindings to ordered `nop` events. Documented mandatory
migration, source-order guarantees, fresh-press behavior, the upstream PushTalk
pending/type-command contract and watchdog/daemon limitations. Inspected upstream
Sway swaymsg source: raw monitored binding events are newline JSON and explicitly
flushed. No actual Sway or audio service was installed or run.

Final regression: `UV_CACHE_DIR=/workspace/work/uv-cache QT_QPA_PLATFORM=offscreen
uv run pytest` passed all 74 tests. `UV_CACHE_DIR=/workspace/work/uv-cache uv run
ruff check` and `git diff --check` passed. Reviewed production, tests, service,
bindings and documentation diffs. PushTalk files/services/configuration and F9 are
untouched; no microphone capture or paid APIs. Live Arch/Sway IPC delivery,
systemd crash/restart behavior and PipeWire remain explicit manual checks. A
responsive daemon is required to honor stop/cancel; an in-flight STT request can
still occupy its six-second timeout. Missed release without detected stream loss
uses the existing 120-second watchdog. No push performed.

## 16 — Immutable capture identities and scoped terminal controls
RED: `QT_QPA_PLATFORM=offscreen UV_CACHE_DIR=/workspace/work/uv-cache uv run
pytest tests/test_voice_lifecycle.py -q` first failed all four regression cases:
delayed stop/cancel workers emitted unscoped terminal operations after a newer
start; release suppressed GUI cancellation; an identity-free transcript callback
adopted the current recording and returned success. Adding two backend lifecycle
regressions produced six failures (two missing-backend imports). No audio/API use.

Design correction: the unchanged PushTalk daemon's watchdog clears recorder state,
then notifies, then increments pending. Its `idle` status is therefore not a
callback-drain fence. A shared static type command cannot recover the originating
recording, even if the status window were narrowed. Studio Buddy will use a separate
token-aware capture backend with the same faster-whisper/sounddevice stack and
warm model. PushTalk itself and F9 remain independent and untouched. The backend
must seal audio and identity together, scope every terminal operation, and carry
the immutable identity through transcription and GUI acceptance. Release does not
advance the generation that supersedes GUI cancellation; only a new start does.

GREEN: the original six cases passed after introducing immutable backend job tokens,
scoped terminal commands, recording generations separate from releases, and rejection
of untagged callbacks. The old `idle` precheck is removed. New presses supersede old
audio/transcripts; one warm model performs inference, with one bounded waiting job.
The sample cap seals capture and token under one lock; no watchdog notification gap
or status sampling can reassign a job's identity. The GUI remains the final durable
acceptance boundary, including callbacks already inside IPC when cancellation occurs.

Focused self-review RED → GREEN:
- A lost start acknowledgement test failed with capture still active. Failed starts
  now durably revoke and attempt generation-scoped backend/GUI cancellation independently.
- Cancel during a newer GUI preparation failed to discard superseded old audio. Only
  cancellation of the current durable generation can now discard such older audio;
  delayed older workers retain their original scope and cannot stop newer capture.
- Shutdown initially revoked after stream.close. A gated close test failed, then
  passed with revocation before potentially slow close and GUI notification afterward.
- Two GUI lock-contention tests failed because cancel returned busy and lost the
  playback interruption. Cancellation now retries on the Qt event loop and validates
  the generation again; ordinary release preserves it, a new recording supersedes it.

REFACTOR: shared JSON socket exchange, short state transactions, immutable CaptureJob,
one capture lock for audio/identity/sealing, and a stable backend owner lock. Updated
existing process tests to the token protocol; replaced the obsolete busy-sttd status
expectation with actual backend lifecycle tests. Added 12 backend tests covering
real Unix IPC and separate delayed worker processes, queued starts after release,
malformed/oversized messages, bounded samples/jobs, model failure recovery, in-flight
old callback rejection by the actual GUI socket, duplicate owners, model-load failure,
shutdown during loading, and socket/mic/lock cleanup. Fake streams/models only.

Packaging now runs `studio-buddy-stt`, installed via the optional `speech` extra.
Heavy dependencies remain lazy and were resolved into uv.lock but not installed or
executed for these tests. The Studio Buddy STT service includes crash revocation and
a ten-second systemd stop deadline. README documents mandatory reinstall/unit restart,
private token transport, supersession/queue behavior, PortAudio and live-check limits.
PushTalk's original daemon, configuration, services and F9 were neither edited nor run.

Regression: full `QT_QPA_PLATFORM=offscreen UV_CACHE_DIR=/workspace/work/uv-cache
uv run pytest` passed 95 tests before the final lint-only cleanup. Ruff initially
reported seven conventions/style findings, which were corrected (the model worker's
broad catch intentionally isolates failed jobs without logging sensitive bodies).
Final post-cleanup checks are recorded below. No microphone capture, paid API calls,
service deployment or push. Actual Arch/Sway event delivery, PipeWire dual streams,
real faster-whisper model load/latency/accuracy and systemd crash handling remain live
checks. A running native inference is not forcibly interrupted on cancel, but its
output is rejected; a new completed capture may wait for it. Backend restarts revoke
old intent and require a fresh press. Five-second control IPC timeouts bound a stuck
control call; capture is capped at 120 seconds of samples even if control is stalled.

Final post-cleanup regression: 95 tests passed in 11.00 seconds with the full command
above. `UV_CACHE_DIR=/workspace/work/uv-cache uv run ruff check` and `git diff --check`
passed. Reviewed production/controller/backend, migrated and new tests, packaging,
README and dependency lock changes. The inspected PushTalk checkout remains clean.
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

## Review fix 3 — Preserve selected observations under a full memory budget
RED: the new desktop-to-OpenAI-payload test failed as expected: an approximately
8,000-character snapshot disappeared when explicit memories filled the context.
The test also checks the total bound and that the next request omits the snapshot.
GREEN: actual request retains the complete selected snapshot plus memory content,
within 12,000 characters, and excludes the snapshot on the next request. REFACTOR:
centralized the AI context limit and composition helper. Regression with Renoise:
37 passed; default installation: 36 passed, 1 optional transport test skipped.
`uv run ruff check`, `git diff --check` and `uv build` passed. Paid services,
actual audio, Arch/Sway and live Renoise remain manual checks; none were run.

## Subscription slice 1 — ChatGPT sign-in and protected session lifecycle
RED: mocked OAuth tests fail collection because `studiobuddy.chatgpt_auth` is absent.
Official SIWC registration, model/inference and session guidance checked 2026-11-07.
Tests will use generated test signing keys and fake remote responses only.
GREEN: 9 OAuth tests passed, including wrong nonce/audience/issuer/expiry rejection
and cancellation closing the callback listener. REFACTOR: adapter centralizes safe
errors and atomic credential writes; file locking serializes rotating refresh tokens.
Regression: 45 passed, 1 optional MCP transport test skipped; Ruff passed.
PyJWT with cryptography is now an intentional runtime dependency for verifying ID
signatures; MCP/server dependencies remain optional. No real login was attempted.

## Subscription slice 2 — Text-only plan inference
RED: subscription inference tests fail collection because `chatgpt_ai` is absent.
GREEN: 6 inference tests passed with fake SSE streams: OAuth-only requests, explicit
terminal completion, failures after partial output, cancellation and no API fallback.
REFACTOR: dedicated subscription adapter preserves the existing request-limit
interface. Regression: 51 passed, 1 optional MCP test skipped; Ruff passed.

## Subscription slice 3 — Desktop account controls and model selection
RED: two UI tests fail because Window has no account/sign-in integration.
Additional RED: the request-contract test fails when it rejects max_output_tokens,
which the official SIWC preview limitations explicitly mark unsupported. Subscription
mode must use a prompt length target, not claim an enforced output-token cap.
GREEN: desktop tests cover sign-in, discovered model selection, persistence, sign-out
and stale login suppression. Subscription requests now omit unsupported output caps.
Additional security regressions passed immediately: forged signatures, returning
registration/identity checks and failed-revocation recovery. REFACTOR: account UI
owns its worker loop and passes only display state to Qt; API mode stays explicit.
Final regression: default installation 56 passed, 1 optional MCP test skipped;
Renoise extra 57 passed. Ruff, package build and git diff --check passed.
Offscreen UI visually inspected at 540x692. Startup/shutdown passed outside the
restricted execution sandbox; the same smoke inside it timed out waiting on an
asyncio worker. No real credentials, browser login or subscription inference used.
The user must complete the documented browser/account/model live check on desktop.

## Integration — merge remote subscription and dependency work
Push was rejected because the remote feature branch had six newer commits. Merged
5f34e8e without rewriting either history. Resolved UI/settings conflicts by retaining
subscription model selection and API reasoning, optional speech and Renoise extras,
and Qt Essentials. Regenerated uv.lock from the combined metadata. Background setup
now documents saved ChatGPT sign-in as well as explicit API credentials; reasoning
selection remains API-only while the subscription adapter uses its model default.
Preserved both development histories and replaced obsolete sttd integration notes.
Validation after conflict resolution: 119 tests passed; Ruff and git diff --check
passed. No microphone capture, paid API calls or live login; hardware checks unchanged.
