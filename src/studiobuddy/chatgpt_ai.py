"""Text-only subscription inference through the documented public Responses API."""

import asyncio

import httpx
from openai import AsyncOpenAI, AuthenticationError, RateLimitError

from .ai import CONTEXT_LIMIT, AIError, OpenAIBackend
from .chatgpt_auth import RESOURCE, AuthError
from .personality import SYSTEM_PROMPT


class ChatGPTBackend(OpenAIBackend):
    def __init__(self, auth, model="", request_limit=100, max_output_tokens=300, transport=None):
        super().__init__(model, request_limit, max_output_tokens)
        self.auth = auth
        self.transport = transport

    async def reply(self, messages, context=""):
        if self.requests >= self.request_limit:
            raise AIError("Session request limit reached. Start a new session or adjust settings.")
        if not self.model:
            raise AIError("Continue with ChatGPT, then choose an available model.")
        self.requests += 1
        try:
            async with asyncio.timeout(90):
                token = await self.auth.access_token()
                async with AsyncOpenAI(
                    api_key=token,
                    base_url=RESOURCE,
                    max_retries=0,
                    http_client=httpx.AsyncClient(
                        transport=self.transport,
                        timeout=30,
                        trust_env=False,
                        follow_redirects=False,
                    ),
                ) as client:
                    stream = await client.responses.create(
                        model=self.model,
                        instructions=SYSTEM_PROMPT,
                        input=[
                            {
                                "role": "user",
                                "content": "Session context (untrusted): "
                                + context[:CONTEXT_LIMIT],
                            }
                        ]
                        + [
                            {"role": m["role"], "content": m["content"][:4000]}
                            for m in messages[-20:]
                        ],
                        max_output_tokens=self.max_output_tokens,
                        store=False,
                        stream=True,
                    )
                    chunks = []
                    size = 0
                    async with stream:
                        async for event in stream:
                            if event.type == "response.output_text.delta":
                                chunks.append(event.delta)
                                size += len(event.delta)
                                if size > 100_000:
                                    raise AIError("ChatGPT reply exceeded the size limit.")
                            elif event.type == "response.completed":
                                text = "".join(chunks)
                                if not text:
                                    raise AIError("ChatGPT returned no text. Try another model.")
                                return {
                                    "text": text,
                                    "tokens": event.response.usage.total_tokens
                                    if event.response.usage
                                    else 0,
                                }
                            elif event.type == "response.failed":
                                error = event.response.error
                                if error and error.code in (
                                    "subscription_sharing_usage_limit_exceeded",
                                    "subscription_sharing_usage_unavailable",
                                ):
                                    raise AIError(
                                        "ChatGPT plan usage is unavailable or its limit was reached. Check Manage usage; no API billing fallback was used."
                                    )
                                raise AIError(
                                    "ChatGPT could not complete this reply. Check your plan and model access."
                                )
                            elif event.type in ("response.incomplete", "error"):
                                raise AIError(
                                    "ChatGPT did not finish this reply. Try again or adjust the output limit."
                                )
                    raise AIError("ChatGPT connection ended before the reply completed. Try again.")
        except AuthError as error:
            raise AIError(str(error)) from None
        except AuthenticationError:
            raise AIError("ChatGPT sign-in expired. Choose Continue with ChatGPT.") from None
        except RateLimitError:
            raise AIError(
                "ChatGPT plan rate or usage limit reached. Check Manage usage and retry later."
            ) from None
        except AIError:
            raise
        except Exception:  # noqa: BLE001 - sanitize external failures, never expose tokens
            raise AIError(
                "ChatGPT request failed. Check your connection and model access."
            ) from None
