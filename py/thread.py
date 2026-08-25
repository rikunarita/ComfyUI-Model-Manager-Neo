import asyncio
import threading
import queue

from . import utils


class DownloadThreadPool:
    def __init__(self) -> None:
        self.workers_count = 0
        self.task_queue = queue.Queue()
        self.running_tasks = set()
        self._lock = threading.Lock()

        default_max_workers = 5
        max_workers: int = default_max_workers
        self.max_worker = max_workers

    def submit(self, task, task_id):
        with self._lock:
            if task_id in self.running_tasks:
                return "Existing"
            self.running_tasks.add(task_id)
            self.task_queue.put((task, task_id))
            return self._adjust_worker_count()

    def _adjust_worker_count(self):
        if self.workers_count < self.max_worker:
            self._start_worker()
            return "Running"
        else:
            return "Waiting"

    def _start_worker(self):
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()
        with self._lock:
            self.workers_count += 1

    def _worker(self):
        loop = asyncio.new_event_loop()
        while True:
            task = None
            task_id = None
            try:
                if self.task_queue.empty():
                    break
                task, task_id = self.task_queue.get()
                loop.run_until_complete(task(task_id))
            except Exception as e:
                utils.print_error(f"worker run error: {str(e)}")
                with self._lock:
                    self.workers_count -= 1
            finally:
                # Always remove task_id from running_tasks to prevent leaks
                # when an error occurs. Previously, only the try block's success
                # path removed the task_id, causing retries to fail.
                if task_id is not None:
                    with self._lock:
                        self.running_tasks.discard(task_id)
