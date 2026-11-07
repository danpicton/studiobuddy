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
