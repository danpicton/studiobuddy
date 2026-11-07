import asyncio


class MockAI:
    async def reply(self, messages, context=""):
        await asyncio.sleep(0.01)
        return {
            "text": "Try duplicating those eight bars, then strip the drums out. Do the chords still carry it?",
            "tokens": 0,
        }
