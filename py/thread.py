import asyncio
from . import utils

class DownloadThreadPool:
    """
    Asyncio-based task manager.
    Runs tasks on the main event loop to ensure WebSocket notifications
    (send_json) work correctly without thread-safety issues or deadlocks.
    """
    def __init__(self):
        # Optimization A-9: bookkeeping used to be split across a `set` of
        # "running" ids and a dict of tasks, which could disagree (an id still
        # in the set after its task finished). A single dict of live tasks is
        # the only source of truth now; "running" == "not done()".
        self.running_tasks: set[str] = set()
        self._tasks: dict[str, asyncio.Task] = {}

    def _get_lock(self) -> asyncio.Lock:
        # Created lazily inside the running loop: building it at import time
        # bound it to no loop at all on Python 3.9.
        lock = getattr(self, "_lock", None)
        if lock is None:
            lock = self._lock = asyncio.Lock()
        return lock

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
        if existing is not None and not existing.done():
            # Same id submitted twice while the first run is still alive:
            # never leave the new, un-awaited coroutine behind (RuntimeWarning).
            close = getattr(coro, "close", None)
            if callable(close):
                close()
            return "Existing"
        if existing is not None:
            self._tasks.pop(task_id, None)
            self.running_tasks.discard(task_id)

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
