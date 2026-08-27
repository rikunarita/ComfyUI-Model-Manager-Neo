import asyncio
from . import utils

class DownloadThreadPool:
    """
    Asyncio-based task manager.
    Unlike the previous threading implementation, this runs tasks on the main
    event loop (aiohttp's loop) to ensure WebSocket notifications (send_json)
    work correctly without thread-safety issues or deadlocks.
    """
    def __init__(self):
        self.running_tasks = set()
        self._lock = asyncio.Lock()

    def submit(self, task_coro, task_id):
        """
        Submit an async coroutine to run on the main event loop.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Fallback for environments where loop isn't running (rare in aiohttp handlers)
            loop = asyncio.get_event_loop()

        async def wrapper():
            try:
                await task_coro
            except Exception as e:
                utils.print_error(f"Task {task_id} failed: {e}")
            finally:
                async with self._lock:
                    self.running_tasks.discard(task_id)

        # Schedule task on the main loop
        task = loop.create_task(wrapper())
        self.running_tasks.add(task_id)
        return "Running"
