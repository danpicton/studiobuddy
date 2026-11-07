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

Voice CLI processes coordinate through `voice-control.lock` in the private runtime
directory. Its per-start token is invalidated by release/cancel. GUI preparation
runs without holding that lock, so a slow GUI cannot make a released key start
capture later. The final token check and STT start are serialized with stop/cancel;
an already-issued daemon start completes before release/cancel is sent. Cancellation
always attempts STT before contacting the GUI, and attempts GUI cancellation even
if STT reports an error. Never remove the lock file while clients are running.
