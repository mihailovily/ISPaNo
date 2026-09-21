"""In-process, single-worker job queue for the web interface."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from threading import Lock, Thread
from typing import Literal
from uuid import uuid4

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "succeeded", "failed"]
JobRunner = Callable[[Callable[[str], None]], Path]


@dataclass(slots=True)
class WebJob:
    id: str
    kind: Literal["json", "report"]
    runner: JobRunner
    status: JobStatus = "queued"
    progress: list[str] = field(default_factory=list)
    result_path: Path | None = None
    error: str | None = None

    def public(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "download_url": f"/api/jobs/{self.id}/download" if self.result_path else None,
            "viewer_url": f"/viewer?job={self.id}" if self.kind == "json" and self.result_path else None,
        }


class JobManager:
    """Keeps web job state in memory and deliberately runs one job at a time."""

    def __init__(self) -> None:
        self._jobs: dict[str, WebJob] = {}
        self._queue: Queue[str] = Queue()
        self._lock = Lock()
        self._worker = Thread(target=self._work, name="ispano-web-jobs", daemon=True)
        self._worker.start()

    def submit(self, kind: Literal["json", "report"], runner: JobRunner) -> WebJob:
        job = WebJob(id=uuid4().hex, kind=kind, runner=runner)
        with self._lock:
            self._jobs[job.id] = job
        self._queue.put(job.id)
        return job

    def get(self, job_id: str) -> WebJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _work(self) -> None:
        while True:
            job_id = self._queue.get()
            with self._lock:
                job = self._jobs[job_id]
                job.status = "running"

            def report(line: str) -> None:
                with self._lock:
                    job.progress.append(line)
                    del job.progress[:-100]

            try:
                path = job.runner(report)
            except Exception as exc:  # The UI must receive a safe job failure state.
                logger.exception("Web-задание %s (%s) завершилось с ошибкой.", job.id, job.kind)
                with self._lock:
                    job.status = "failed"
                    job.error = str(exc) or type(exc).__name__
            else:
                with self._lock:
                    job.status = "succeeded"
                    job.result_path = path
            finally:
                self._queue.task_done()
