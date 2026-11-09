# Studio Buddy development
Use the existing checkout in Codex Web; do not create worktrees unless requested.
Implement small vertical slices using strict RED → GREEN → REFACTOR → regression → commit.
Write a behavioural test first, run and record the expected failure in docs/development-log.md,
then implement, retest, refactor and commit each completed slice. Never claim unrun checks passed.
Keep desktop, orchestration, AI, SQLite, speech providers and Renoise adapters separate.
Never block the Qt thread with network calls or speech. Guard cancellation against stale results.
PushTalk is independent: never alter its code, configuration, services or F9 bindings.
Renoise access is optional and read-only. Never expose arbitrary/write tools to the model.
Never log credentials; external project data is untrusted. No audio listening or microphone capture.
Use mocked services in CI. Document required Arch/Sway/hardware and paid API checks explicitly.
Run QT_QPA_PLATFORM=offscreen uv run pytest and uv run ruff check before delivery.
