# Required live checks (not performed in Codex Web)

Use a disposable musical session. No project edits should occur.

1. Arch/Sway: install, launch, type, paste, Ctrl+Enter; confirm readable UI at your
   scale, app_id with `swaymsg -t get_tree`, focus/scratchpad bindings and no always-on-top.
2. Existing PushTalk: focus input, hold/release existing F9, verify dictation and edit
   before sending. Verify its services/config/bindings are unchanged; no second mic.
3. ChatGPT: run the normal app, Continue with ChatGPT, approve plan usage, select
   a discovered model and send one message. Verify account label, reply and token
   count, restart persistence, refresh after token expiry, Cancel sign-in and Sign out.
   Verify the default browser returns to the loopback callback on Arch/Sway. Check
   Manage usage; confirm plan-limit failures never switch to API billing. Actual
   account eligibility and inference remain unverified until this check succeeds.
   Optional API mode: explicitly select api with your own API key/billing and test.
4. Piper: install a licensed model + JSON, select it, Test Voice; verify normal audio
   output. While generating/playing press Stop, send another message and switch to Text.
   Old speech must never begin/resume. Remove model temporarily and verify text survives.
5. ElevenLabs and Hume separately: select a voice you can access, test once (paid),
   verify pronunciation/settings; interrupt while downloading/playing. Test local Piper
   fallback and text fallback. No unselected cloud service should receive text.
6. Create two projects/sessions, record favourite/rejected ideas and outcomes, wrap up,
   restart, edit/delete notes; verify isolation, restored goal/history and next-step context.
7. Renoise: first verify the exact tool's documentation and protocol. This build only
   supports MCP Streamable HTTP resources. Connect a compatible local read-only server,
   discover resources, select/read a bounded resource, send one chat message. Disconnect
   and verify chat works. Unsupported tool-only servers must not trigger calls or writes.
   Specific ReMCP compatibility remains unresolved; do not treat a fake server as proof.
8. Shut down during API request/generation/playback; ensure no orphan audio processes.
   Back up the closed data directory and verify recovery on a copy.

CI mocks do not establish hardware, Sway, provider account or ReMCP compatibility.
