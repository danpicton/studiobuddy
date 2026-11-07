# Integration references and decisions

Consulted during implementation (2026-11-07):

- OpenAI official Python SDK README: https://github.com/openai/openai-python
  Responses API, AsyncOpenAI, timeout/retries and output_text. SDK 2.54.0 locked.
- Piper official CLI: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md
  `piper -m MODEL -f OUTPUT` with text on stdin. No model downloads in app.
- ElevenLabs official SDK reference and API payload:
  https://github.com/elevenlabs/elevenlabs-python/blob/main/reference.md
  POST `/v1/text-to-speech/{voice_id}`, xi-api-key, voice_settings and MP3 output.
- Hume official SDK source:
  https://github.com/HumeAI/hume-python-sdk/blob/main/src/hume/tts/raw_client.py
  https://github.com/HumeAI/hume-python-sdk/blob/main/src/hume/tts/types/posted_utterance.py
  POST `/v0/tts/file`, X-Hume-Api-Key, utterances with voice.id, description, speed.
- Official MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
  Installed 1.30.0 ClientSession and streamable_http_client interfaces.
- Requested Renoise page: https://www.renoise.com/tools/renoise-mcp — denied by
  environment egress policy. Draft adds this domain, pending environment settings save.
  Accessible https://github.com/zakhap/renoise-mcp lists write operations/evaluate_lua;
  no such tool is used. Its identity with the requested tool is not established.

Cloud speech uses direct documented HTTP APIs through httpx rather than extra SDKs.
Cancellation closes the HTTP stream; file playback is a cancellable ffplay child.
All network workers run outside Qt's UI thread. OpenAI never receives a tools schema.
No key values are written in errors, config or logs. MCP resource text stays in the
user context channel and is explicitly marked untrusted, bounded and single-request.

## Dedicated PushTalk integration
Inspected https://github.com/danpicton/pushtalk main: existing `sttd --type-cmd`
sends UTF-8 transcript bytes on stdin; `sttctl --socket` controls an independent
instance. No upstream modifications. Dedicated sockets/state avoid F9 conflicts.
The dedicated instance uses small.en/CPU/int8, four threads, no pre-roll; model
download cache is shared, model RAM and mic streams are separate. No paid STT.
Studio Buddy's private local socket uses bounded newline JSON and a lock file;
no TCP listener, focus injection, model tools or automatic memory writes.

The persistent `studio-buddy-voice listen-sway` process subscribes to Sway's
ordered `binding` IPC events using `swaymsg -r -m`. Inspected upstream
[swaymsg source](https://github.com/swaywm/sway/blob/master/swaymsg/main.c):
raw monitored events are one JSON object per line, flushed after each event. The supplied `nop` bindings
carry actions directly in that stream; they do not spawn independent key-command
processes. The listener assigns a unique identity and registers intent synchronously
before dispatching any blocking work. The causal guarantee is stream order, not
UUID order or process scheduling. Standalone CLI `start` is rejected. Events not
observed before subscription are never inferred; startup/disconnect/shutdown revoke
old intent and require a fresh press. A lock prevents duplicate listeners. The unit
also cancels in ExecStopPost, covering crashes/SIGKILL when Python cleanup cannot run.

Two stable lock files in the private runtime directory have separate responsibilities.
`voice-control.lock` serializes STT operations; `voice-state.lock` protects intent,
recording identity and cancellation revision in atomically replaced `voice-state.json`.
An interrupted write leaves the previous state usable for crash cleanup.
State transactions contain no socket
or STT waits. Release revokes pending starts; cancel also revokes transcript acceptance
before either IPC operation. GUI cancellation and recorder cancellation run independently,
so a hung/unavailable GUI cannot prevent the recorder attempt and a slow recorder
cannot leave transcripts eligible. GUI start/submit requests carry recording identity;
GUI cancel carries revision so an old callback cannot cancel a newer recording.
The GUI uses a nonblocking state lock and rejects a command if that lock is busy.
Acceptance and cancellation linearize under that lock: an already-accepted transcript
cannot be retroactively unsent; any submit after revocation is rejected before SQLite/AI.

Unmodified PushTalk's worker keeps `pending` nonzero until its synchronous type-command
subprocess exits (including timeout/kill). Status therefore remains `transcribing`
until callbacks drain; Studio Buddy requires `idle` before assigning a new recording.
The callback snapshots the recording identity before GUI IPC, so a delayed socket
message cannot attach to a later recording. This integration depends on that upstream
status/type-command contract and exclusive use of Studio Buddy's dedicated daemon;
do not send it unrelated `sttctl start` commands. No PushTalk file or F9 binding changes.

STT IPC remains bounded by its six-second subprocess timeout. An in-flight STT start
is serialized before a later stop/cancel; cancellation cannot promise a responsive
microphone daemon when that daemon itself is hung. Missed releases without a detected
stream failure remain bounded by PushTalk's configured 120-second watchdog. Live
Sway delivery, service lifecycle and microphone behavior still require hardware checks.
Never remove lock files while clients are running.
