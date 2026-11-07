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
