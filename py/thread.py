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
        # BUG FIX: the lock used to be created here, i.e. at import time and
        # therefore OUTSIDE any running event loop. On Python 3.9 (where
        # asyncio.Lock() still binds eagerly) that produced "got Future
        # attached to a different loop" as soon as a task finished. Create it
        # lazily inside the running loop instead — a no-op on 3.10+, correct
        # everywhere.
        self._lock: asyncio.Lock | None = None
        self._tasks = {}

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def submit(self, coro, task_id):
        """
        Submit a coroutine to run as a background task on the main loop.

        Returns "Existing" when a task with the same id is already running.
        BUG FIX: this guard was lost in the thread-pool -> asyncio rewrite.
        Without it, pressing "resume" twice (or resuming a task that is still
        running) started two concurrent downloads writing to the SAME
        `<task_id>.download` file, corrupting the model.
        """
        existing = self._tasks.get(task_id)
        if task_id in self.running_tasks:
            if existing is None or existing.done():
                # Stale bookkeeping (the coroutine already finished but its
                # `finally` has not run yet): clean up and start the new one.
                self.running_tasks.discard(task_id)
                self._tasks.pop(task_id, None)
            else:
                # Never leave an un-awaited coroutine behind (RuntimeWarning).
                close = getattr(coro, "close", None)
                if callable(close):
                    close()
                return "Existing"

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
                async with self._get_lock():
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
