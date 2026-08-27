import asyncio
from . import utils

class DownloadThreadPool:
    """
    Asyncio-based task manager.
    Runs tasks on the main event loop to ensure WebSocket notifications
    (send_json) work correctly without thread-safety issues or deadlocks.
    """
    def __init__(self):
        self.running_tasks = set()
        self._lock = asyncio.Lock()
        self._tasks = {}

    def submit(self, coro, task_id):
        """
        Submit a coroutine to run as a background task on the main loop.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        async def wrapper():
            try:
                await coro
            except asyncio.CancelledError:
                utils.print_info(f"Task {task_id} was cancelled.")
            except Exception as e:
                utils.print_error(f"Task {task_id} failed: {e}")
            finally:
                async with self._lock:
                    self.running_tasks.discard(task_id)
                    self._tasks.pop(task_id, None)

        task = loop.create_task(wrapper())
        self.running_tasks.add(task_id)
        self._tasks[task_id] = task
        return "Running"

    def cancel(self, task_id):
        task = self._tasks.get(task_id)
        if task and not task.done():
            task.cancel()
