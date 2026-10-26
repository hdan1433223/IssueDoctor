from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

from flask import Flask


class TaskManager:
    def __init__(self, app: Flask, *, max_workers: int = 1) -> None:
        if max_workers not in {1, 2}:
            raise ValueError("TASK_MAX_WORKERS 只允许 1 或 2")
        self._app = app
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="issuedoctor-analysis",
        )

    def submit(self, run_id: str, runner: Callable[[str], None] | None = None) -> Future:
        task_runner = runner or self._default_runner
        return self._executor.submit(self._run_in_context, task_runner, run_id)

    def _run_in_context(self, runner: Callable[[str], object], run_id: str) -> object:
        with self._app.app_context():
            return runner(run_id)

    @staticmethod
    def _default_runner(run_id: str) -> None:
        from issuedoctor.tasks.analysis_task import run_analysis

        run_analysis(run_id)

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=False)
