"""Data models returned by the SDK."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Any, Dict


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class ConversionResult:
    """Result of `client.convert(...)`.

    Three possible shapes, depending on model/output:
    - binary xlsx: `content` is bytes, `format='xlsx'`
    - txt: `content` is bytes/str, `format='txt'`
    - json metadata: `data` is a dict, `format='json'`
    """

    content: Optional[bytes] = None
    data: Optional[Dict[str, Any]] = None
    format: str = "xlsx"
    request_id: Optional[str] = None
    pages_used: Optional[int] = None
    model: Optional[str] = None

    def save(self, path: str) -> None:
        """Write the content to disk. For format='json', use data via .json instead."""
        if self.content is None:
            raise ValueError(
                "ConversionResult has no binary content (format=json). "
                "Use `result.data` or `result.json()` instead."
            )
        with open(path, "wb") as f:
            f.write(self.content)

    def text(self) -> str:
        """Decode as UTF-8 — useful for format='txt'."""
        if self.content is None:
            return ""
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Dict[str, Any]:
        """Return the data dict (format='json'), or raise."""
        if self.data is None:
            raise ValueError("ConversionResult has no JSON data (format != 'json')")
        return self.data


@dataclass
class JobResult:
    """Result wrapper for /v1/jobs/{id}/result.

    Two shapes:
    - R2 signed URL: `result_url` is set, `expires_in` in seconds
    - direct binary file: `content` bytes
    """

    result_url: Optional[str] = None
    expires_in: Optional[int] = None
    content: Optional[bytes] = None
    content_type: Optional[str] = None

    def save(self, path: str) -> None:
        """Save the file. If result_url is set, download it from the signed URL."""
        if self.content is not None:
            with open(path, "wb") as f:
                f.write(self.content)
            return
        if self.result_url:
            import urllib.request
            with urllib.request.urlopen(self.result_url, timeout=60) as resp:
                data = resp.read()
            with open(path, "wb") as f:
                f.write(data)
            return
        raise ValueError("JobResult has neither content nor result_url")


@dataclass
class Job:
    """Async job. Returned by create_job() and get_job().

    Use `job.wait()` to poll until `done`/`failed`.
    """

    request_id: str
    status: JobStatus
    model: Optional[str] = None
    pages_used: Optional[int] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_detail: Optional[str] = None
    filename: Optional[str] = None  # set on jobs created by batch(): the uploaded file's name
    _client: Any = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, d: dict, client=None) -> "Job":
        return cls(
            request_id=d.get("request_id", ""),
            status=JobStatus(d.get("status", "pending")),
            model=d.get("model"),
            pages_used=d.get("pages_used"),
            created_at=d.get("created_at"),
            completed_at=d.get("completed_at"),
            error_detail=d.get("error_detail"),
            _client=client,
        )

    @property
    def is_done(self) -> bool:
        return self.status == JobStatus.DONE

    @property
    def is_failed(self) -> bool:
        return self.status == JobStatus.FAILED

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.DONE, JobStatus.FAILED)

    def refresh(self) -> "Job":
        """Re-read the status from the server. Requires the original client."""
        if self._client is None:
            raise RuntimeError("Job not bound to a client (use client.get_job(request_id))")
        updated = self._client.get_job(self.request_id)
        # update the fields in place
        self.status = updated.status
        self.pages_used = updated.pages_used
        self.completed_at = updated.completed_at
        self.error_detail = updated.error_detail
        return self

    def wait(self, timeout: float = 600.0, initial_delay: float = 1.0,
             max_delay: float = 15.0) -> "Job":
        """Poll with exponential backoff until the status is terminal.

        timeout: total seconds before raising TimeoutError.
        Default: 10 min, retries at 1s,2s,4s,8s,15s,15s,...
        """
        import time
        deadline = time.monotonic() + timeout
        delay = initial_delay
        while True:
            self.refresh()
            if self.is_terminal:
                return self
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Job {self.request_id} still {self.status.value} after {timeout}s"
                )
            time.sleep(min(delay, max(0.1, deadline - time.monotonic())))
            delay = min(delay * 2, max_delay)

    def get_result(self) -> JobResult:
        """Fetch /v1/jobs/{id}/result. Raises NotReady if status != done."""
        if self._client is None:
            raise RuntimeError("Job not bound to a client")
        return self._client.get_job_result(self.request_id)

    def download(self, path: str) -> None:
        """Shortcut: get_result().save(path)."""
        self.get_result().save(path)

    def delete(self) -> None:
        """Delete the job and clean up its files."""
        if self._client is None:
            raise RuntimeError("Job not bound to a client")
        self._client.delete_job(self.request_id)


@dataclass
class BatchResult:
    """Result of `client.batch(...)`. Mixed: created jobs + per-file errors."""

    batch_id: str
    model: str
    jobs: List[Job] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def jobs_created(self) -> int:
        return len(self.jobs)

    def wait_all(self, timeout: float = 1200.0, parallel: bool = True, max_workers: int = 10) -> List[Job]:
        """Poll until every job reaches a terminal state.

        Args:
            timeout: seconds for each individual job
            parallel: if True (default), uses a ThreadPoolExecutor to poll in parallel.
                For 20 jobs, ~20× faster than sequential polling when network-bound.
            max_workers: max threads (default 10). The work is I/O-bound, so raising it is safe.
        """
        if not parallel or len(self.jobs) <= 1:
            return [j.wait(timeout=timeout) for j in self.jobs]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(max_workers, len(self.jobs))) as ex:
            return list(ex.map(lambda j: j.wait(timeout=timeout), self.jobs))
