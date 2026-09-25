"""Main client for the myocr.app v1 API.

All methods raise subclasses of MyOCRError on API error codes.
Automatic retry on 429 and 5xx (3 attempts, exponential backoff 1s/2s/4s).
"""
import logging
import os
import time
from typing import Optional, BinaryIO, Union, List, IO

try:
    import requests
except ImportError:
    raise ImportError(
        "myocr-client requires `requests`. Install with: pip install requests"
    )

from .exceptions import (
    MyOCRError,
    MissingApiKey,
    RateLimited,
    InternalError,
    from_response,
)
from ._version import __version__
from .models import ConversionResult, Job, JobResult, BatchResult, JobStatus


DEFAULT_BASE_URL = "https://api.myocr.app"
DEFAULT_TIMEOUT = 60  # seconds
DEFAULT_RETRY_ATTEMPTS = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

logger = logging.getLogger(__name__)


def _looks_like_path(file: Union[str, BinaryIO, bytes]) -> bool:
    return isinstance(file, str) and os.path.exists(file)


def _prepare_file_tuple(file, filename: Optional[str] = None):
    """Normalize the file input into a (filename, fileobj-or-bytes) tuple for requests."""
    if isinstance(file, (bytes, bytearray)):
        return (filename or "upload.pdf", bytes(file))
    if hasattr(file, "read"):
        name = filename or getattr(file, "name", None) or "upload.pdf"
        if isinstance(name, str) and os.sep in name:
            name = os.path.basename(name)
        return (name, file)
    if isinstance(file, str):
        return (filename or os.path.basename(file), open(file, "rb"))
    raise TypeError(f"file must be a path, file-like, or bytes; got {type(file)!r}")


def _add_optional(data: dict, **kwargs) -> dict:
    """Add only the parameters that have a value to the form; lists become CSV.

    Needed for page_range and fields: if they were always sent, even when empty, the server
    would read them as an empty string instead of as 'absent'.
    """
    for name, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = ",".join(str(v).strip() for v in value if str(v).strip())
        value = str(value).strip()
        if value:
            data[name] = value
    return data


class MyOCRClient:
    """HTTP client for the myocr.app API.

    Args:
        api_key: an 'sk_live_...' or 'sk_test_...' key (or read from the MYOCR_API_KEY env var)
        base_url: defaults to https://api.myocr.app (override for staging: beta.myocr.app)
        timeout: seconds for each HTTP request
        retry_attempts: total attempts on 429 and 5xx (default 3)
        session: optional pre-configured requests.Session (proxies, certificates)

    Example:
        from myocr_client import MyOCRClient
        client = MyOCRClient(api_key="sk_live_...")
        result = client.convert("invoice.pdf", model="invoice")
        result.save("out.xlsx")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        session: Optional["requests.Session"] = None,
    ):
        self.api_key = api_key or os.environ.get("MYOCR_API_KEY", "").strip()
        if not self.api_key:
            raise MissingApiKey(
                "api_key required (pass as argument or set MYOCR_API_KEY env var)"
            )
        self.base_url = (base_url or os.environ.get("MYOCR_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.retry_attempts = max(1, retry_attempts)
        self._session = session or requests.Session()

    def _headers(self) -> dict:
        return {
            "X-API-Key": self.api_key,
            "User-Agent": f"myocr-client-python/{__version__}",
        }

    def _request(self, method: str, path: str, **kwargs) -> "requests.Response":
        """HTTP request with retry on 429/5xx."""
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        kwargs.setdefault("timeout", self.timeout)

        last_exc = None
        for attempt in range(self.retry_attempts):
            try:
                resp = self._session.request(method, url, headers=headers, **kwargs)
            except requests.RequestException as e:
                last_exc = e
                if attempt < self.retry_attempts - 1:
                    delay = 2 ** attempt
                    logger.warning(f"[myocr] {method} {path} network error attempt {attempt + 1}: {e}; retry in {delay}s")
                    time.sleep(delay)
                    continue
                raise InternalError(f"network error: {e}", status_code=0) from e

            if resp.status_code in RETRYABLE_STATUS and attempt < self.retry_attempts - 1:
                # Honor Retry-After if present
                retry_after = resp.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2 ** attempt
                except (TypeError, ValueError):
                    delay = 2 ** attempt
                logger.warning(f"[myocr] {method} {path} → {resp.status_code} attempt {attempt + 1}; retry in {delay}s")
                time.sleep(delay)
                continue
            return resp
        if last_exc:
            raise InternalError(str(last_exc), status_code=0) from last_exc
        return resp  # type: ignore

    def _raise_if_error(self, resp: "requests.Response") -> None:
        """If the response is not 2xx, raise the appropriate exception."""
        if 200 <= resp.status_code < 300:
            return
        request_id = resp.headers.get("X-MyOCR-Request-Id")
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        raise from_response(resp.status_code, body, request_id=request_id)

    # ---------- Status ----------

    def status(self) -> dict:
        """GET /v1/status — public health check (no auth required, but the API key is sent anyway)."""
        resp = self._request("GET", "/v1/status")
        self._raise_if_error(resp)
        return resp.json().get("data", {})

    def usage(self) -> dict:
        """GET /v1/usage — current quota for your API key.
        Returns a dict with plan/calls_used/calls_limit/percentage/reset_date/year_month/is_test_key.
        Useful for checking programmatically when you are approaching the limit."""
        resp = self._request("GET", "/v1/usage")
        self._raise_if_error(resp)
        return resp.json().get("data", {})

    # ---------- Sync conversion ----------

    def convert(
        self,
        file: Union[str, bytes, IO[bytes]],
        model: str = "tables",
        output: str = "xlsx",
        filename: Optional[str] = None,
        page_range: Optional[str] = None,
        fields: Optional[Union[str, List[str]]] = None,
        fields_mode: Optional[str] = None,
    ) -> ConversionResult:
        """POST /v1/convert — sync, max 5MB / 10 pages.

        Args:
            file: path string, bytes, or a file-like object opened in 'rb' mode
            model: tables / text / invoice / receipt / bank_statement / business_card / fields
            output: xlsx / txt / json
            filename: original file name (useful if file is bytes or a file-like object without .name)
            page_range: PDF only — '3', '3-5', '1,3-5', '2-' (to the end). Excluded pages
                are not billed. For a mixed document (invoice + detail attachments), it is
                better to make one call with model='invoice' on the invoice page and one
                with model='tables' on the attachment pages.
            fields: required with model='fields' — the names of the columns you want,
                as a list or a comma-separated string (max 60)
            fields_mode: 'page' (default) for one row per page, or 'list' when the
                document is a printed list and each entry should become a row
                (values are assigned by position)

        Returns:
            ConversionResult with .content (bytes) or .data (dict for output=json).

        Raises:
            QuotaExceeded, FileTooLarge, TooManyPages, OcrEngineError, RateLimited, ...
        """
        file_tuple = _prepare_file_tuple(file, filename=filename)
        files = {"file": file_tuple}
        data = {"model": model, "output": output}
        _add_optional(data, page_range=page_range, fields=fields, fields_mode=fields_mode)
        try:
            resp = self._request("POST", "/v1/convert", files=files, data=data)
        finally:
            # if we opened the file ourselves, close it
            if isinstance(file, str) and hasattr(file_tuple[1], "close"):
                try:
                    file_tuple[1].close()
                except Exception:
                    pass

        self._raise_if_error(resp)

        request_id = resp.headers.get("X-MyOCR-Request-Id")
        pages_used_h = resp.headers.get("X-MyOCR-Pages-Used")
        pages_used = int(pages_used_h) if pages_used_h and pages_used_h.isdigit() else None
        model_used = resp.headers.get("X-MyOCR-Model") or model

        ctype = resp.headers.get("Content-Type", "").lower()
        if "application/json" in ctype:
            body = resp.json()
            return ConversionResult(
                data=body.get("data") if isinstance(body, dict) else body,
                format="json",
                request_id=request_id,
                pages_used=pages_used,
                model=model_used,
            )
        if "text/plain" in ctype:
            return ConversionResult(
                content=resp.content,
                format="txt",
                request_id=request_id,
                pages_used=pages_used,
                model=model_used,
            )
        return ConversionResult(
            content=resp.content,
            format="xlsx",
            request_id=request_id,
            pages_used=pages_used,
            model=model_used,
        )

    # ---------- Async jobs ----------

    def create_job(
        self,
        file: Union[str, bytes, IO[bytes]],
        model: str = "tables",
        webhook_url: Optional[str] = None,
        filename: Optional[str] = None,
        page_range: Optional[str] = None,
        fields: Optional[Union[str, List[str]]] = None,
        fields_mode: Optional[str] = None,
    ) -> Job:
        """POST /v1/jobs — async, max 50MB.

        page_range: PDF only — '3', '3-5', '1,3-5', '2-'. Excluded pages are not charged.
        fields: required with model='fields' (a list or a comma-separated string).
        fields_mode: 'page' (default) or 'list' for printed lists.
        """
        file_tuple = _prepare_file_tuple(file, filename=filename)
        files = {"file": file_tuple}
        data = {"model": model}
        if webhook_url:
            data["webhook_url"] = webhook_url
        _add_optional(data, page_range=page_range, fields=fields, fields_mode=fields_mode)
        try:
            resp = self._request("POST", "/v1/jobs", files=files, data=data)
        finally:
            if isinstance(file, str) and hasattr(file_tuple[1], "close"):
                try:
                    file_tuple[1].close()
                except Exception:
                    pass

        self._raise_if_error(resp)
        body = resp.json().get("data", {})
        return Job.from_dict(body, client=self)

    def get_job(self, request_id: str) -> Job:
        """GET /v1/jobs/{id}."""
        resp = self._request("GET", f"/v1/jobs/{request_id}")
        self._raise_if_error(resp)
        return Job.from_dict(resp.json().get("data", {}), client=self)

    def get_job_result(self, request_id: str) -> JobResult:
        """GET /v1/jobs/{id}/result — R2 signed URL or binary file."""
        resp = self._request("GET", f"/v1/jobs/{request_id}/result")
        self._raise_if_error(resp)
        ctype = resp.headers.get("Content-Type", "").lower()
        if "application/json" in ctype:
            body = resp.json().get("data", {})
            return JobResult(
                result_url=body.get("result_url"),
                expires_in=body.get("expires_in"),
            )
        return JobResult(
            content=resp.content,
            content_type=ctype or None,
        )

    def delete_job(self, request_id: str) -> dict:
        """DELETE /v1/jobs/{id}."""
        resp = self._request("DELETE", f"/v1/jobs/{request_id}")
        self._raise_if_error(resp)
        return resp.json().get("data", {})

    # ---------- Batch ----------

    def batch(
        self,
        files: List[Union[str, bytes, IO[bytes]]],
        model: str = "tables",
        webhook_url: Optional[str] = None,
        filenames: Optional[List[str]] = None,
        page_range: Optional[str] = None,
        fields: Optional[Union[str, List[str]]] = None,
        fields_mode: Optional[str] = None,
    ) -> BatchResult:
        """POST /v1/batch — 1-20 files in a single call.

        page_range applies to ALL files in the batch: use it when they share the same layout.
        """
        if not files:
            raise ValueError("files list cannot be empty")
        if len(files) > 20:
            raise ValueError("max 20 files per batch")

        names = filenames or [None] * len(files)
        if len(names) != len(files):
            raise ValueError("filenames length must match files length")

        multi_files = []
        opened = []
        for f, name in zip(files, names):
            tup = _prepare_file_tuple(f, filename=name)
            multi_files.append(("files", tup))
            if isinstance(f, str):
                opened.append(tup[1])

        data = {"model": model}
        if webhook_url:
            data["webhook_url"] = webhook_url
        _add_optional(data, page_range=page_range, fields=fields, fields_mode=fields_mode)

        try:
            resp = self._request("POST", "/v1/batch", files=multi_files, data=data)
        finally:
            for fh in opened:
                try:
                    fh.close()
                except Exception:
                    pass

        self._raise_if_error(resp)
        body = resp.json().get("data", {})
        return BatchResult(
            batch_id=body.get("batch_id", ""),
            model=body.get("model", model),
            jobs=[
                Job(
                    request_id=j.get("request_id", ""),
                    status=JobStatus(j.get("status", "pending")),
                    model=body.get("model", model),
                    filename=j.get("filename"),
                    _client=self,
                )
                for j in body.get("jobs", [])
            ],
            errors=body.get("errors", []),
        )

    # ---------- API keys (require a user login session, not X-API-Key) ----------
    # Exposed for completeness; in practice keys are managed from the /account/api dashboard.

    def list_keys(self) -> List[dict]:
        """GET /v1/keys — list the user's keys (requires a session cookie, not X-API-Key)."""
        resp = self._request("GET", "/v1/keys")
        self._raise_if_error(resp)
        return resp.json().get("data", [])

    def rotate_key(self, key_id: int) -> dict:
        """POST /v1/keys/{id}/rotate — atomically revokes the key and issues a new one.
        Returns a dict with 'key' (raw), shown only once. Store it immediately.
        Requires a login session (not X-API-Key)."""
        resp = self._request("POST", f"/v1/keys/{key_id}/rotate")
        self._raise_if_error(resp)
        return resp.json().get("data", {})

    def list_jobs(
        self,
        status: Optional[str] = None,
        model: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """GET /v1/jobs — paginated list of jobs for your api_key.
        Filters: status (pending/processing/done/failed), model. limit max 100.
        Returns {total, limit, offset, jobs: [...]}."""
        params = {"limit": str(min(limit, 100)), "offset": str(max(offset, 0))}
        if status:
            params["status"] = status
        if model:
            params["model"] = model
        from urllib.parse import urlencode
        resp = self._request("GET", f"/v1/jobs?{urlencode(params)}")
        self._raise_if_error(resp)
        return resp.json().get("data", {})
