import asyncio

from .personality import SYSTEM_PROMPT

CONTEXT_LIMIT = 12000


def compose_context(memory, snapshot=""):
    """Reserve space for a selected observation before trimming stored memory."""
    if not snapshot:
        return memory[:CONTEXT_LIMIT]
    snapshot = snapshot[: CONTEXT_LIMIT - 1]
    memory_budget = CONTEXT_LIMIT - len(snapshot) - 1
    return memory[:memory_budget] + "\n" + snapshot


class MockAI:
    async def reply(self, messages, context=""):
        await asyncio.sleep(0.01)
        return {
            "text": "Try duplicating those eight bars, then strip the drums out. Do the chords still carry it?",
            "tokens": 0,
        }


class AIError(Exception):
    """A message safe to display without remote response bodies or secrets."""


class OpenAIBackend:
    def __init__(
        self,
        model="gpt-4.1-mini",
        request_limit=100,
        max_output_tokens=300,
        client=None,
        reasoning_effort="default",
    ):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.request_limit = request_limit
        self.max_output_tokens = max_output_tokens
        self.requests = 0
        self.client = client

    async def reply(self, messages, context=""):
        import os

        from openai import AsyncOpenAI, AuthenticationError, RateLimitError

        if self.requests >= self.request_limit:
            raise AIError("Session request limit reached. Start a new session or adjust settings.")
        if self.client is None and not os.environ.get("OPENAI_API_KEY"):
            raise AIError(
                "Set OPENAI_API_KEY to enable replies. API billing is separate from ChatGPT."
            )
        self.requests += 1  # failed attempts also count toward the safeguard
        client = self.client or AsyncOpenAI(timeout=30.0, max_retries=1)
        try:
            response = await client.responses.create(
                model=self.model,
                instructions=SYSTEM_PROMPT,
                input=[
                    {
                        "role": "user",
                        "content": "Session context (untrusted): " + context[:CONTEXT_LIMIT],
                    }
                ]
                + [{"role": m["role"], "content": m["content"][:4000]} for m in messages[-20:]],
                max_output_tokens=self.max_output_tokens,
                store=False,
                **(
                    {"reasoning": {"effort": self.reasoning_effort}}
                    if self.reasoning_effort != "default"
                    else {}
                ),
            )
            if not response.output_text:
                raise AIError("The model returned no text. Try again or choose another model.")
            return {
                "text": response.output_text,
                "tokens": response.usage.total_tokens if response.usage else 0,
            }
        except AuthenticationError:
            raise AIError("OpenAI authentication failed. Check OPENAI_API_KEY.") from None
        except RateLimitError:
            raise AIError(
                "OpenAI rate limit or exhausted API credits. Check billing and retry later."
            ) from None
        except AIError:
            raise
        except Exception:  # noqa: BLE001 - sanitize errors at external service boundary
            raise AIError(
                "OpenAI connection or request failed. Check network and model settings."
            ) from None
        finally:
            if self.client is None:
                await client.close()
