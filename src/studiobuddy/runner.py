"""One cancellable asyncio loop; results cross into Qt through signals."""

import asyncio
import threading
from PySide6.QtCore import QObject, Signal


class Runner(QObject):
    done = Signal(int, object, object)

    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.futures = set()

    def submit(self, token, coroutine):
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        self.futures.add(future)

        def finish(f):
            self.futures.discard(f)
            if f.cancelled():
                return
            try:
                result = f.result()
            except Exception as exc:
                self.done.emit(token, None, exc)
            else:
                self.done.emit(token, result, None)

        future.add_done_callback(finish)
        return future

    def close(self):
        if self.loop.is_closed():
            return

        async def shutdown():
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        asyncio.run_coroutine_threadsafe(shutdown(), self.loop).result(timeout=5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        self.loop.close()
