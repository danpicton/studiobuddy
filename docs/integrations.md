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


## ChatGPT plan integration (2026-11-07)

Studio Buddy uses the official direct local-app flow, not Codex app-server or
private ChatGPT endpoints:

- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations

OAuth uses PKCE/state/nonce and a temporary loopback listener. PyJWT/cryptography
verifies identity signatures. Protected app-owned storage and a file lock support
rotating refresh tokens. Responses use OAuth, explicit public API URLs, store=false,
stream=true, no tools and no automatic API-key fallback. The model catalogue comes
from the connected account. The subscription preview rejects max_output_tokens;
the length setting is therefore only a prompt target in subscription mode.
This personal app keeps one account registration. Account eligibility, browser
round-trip and a real subscription reply require the user's live desktop check.
