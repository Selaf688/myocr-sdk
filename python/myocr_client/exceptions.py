"""1:1 mapping of the v1 API error codes (see https://www.myocr.app/docs/api/openapi.json).

All custom exceptions inherit from MyOCRError. The client raises them
based on the `error.code` field of the JSON envelope, or on the HTTP status
when the body is not JSON.

Example:
    try:
        client.convert("doc.pdf", model="invoice")
    except QuotaExceeded as e:
        print(e.upgrade_url)
    except InvalidApiKey:
        print("revoke or rotate key")
"""
from typing import Optional


class MyOCRError(Exception):
    """Base class for all SDK exceptions."""

    def __init__(
        self,
        message: str = "",
        *,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
        status_code: Optional[int] = None,
        payload: Optional[dict] = None,
    ):
        super().__init__(message or code or "myocr error")
        self.code = code
        self.message = message
        self.request_id = request_id
        self.status_code = status_code
        self.payload = payload or {}

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(code={self.code!r}, "
            f"status={self.status_code}, request_id={self.request_id!r}, "
            f"message={self.message!r})"
        )


class MissingApiKey(MyOCRError):
    """X-API-Key header is missing."""


class InvalidApiKey(MyOCRError):
    """Key not found or revoked."""


class UnsupportedModel(MyOCRError):
    """The model parameter is not one of tables/text/invoice/receipt/bank_statement/business_card/fields."""


class UnsupportedFileType(MyOCRError):
    """File extension not supported."""


class MissingFile(MyOCRError):
    """Multipart file is missing or empty."""


class FileTooLarge(MyOCRError):
    """File exceeds 5MB (sync) or 50MB (async)."""


class TooManyPages(MyOCRError):
    """Document exceeds 10 pages on the sync flow."""


class InvalidWebhookUrl(MyOCRError):
    """webhook_url is not http(s)://."""


class QuotaExceeded(MyOCRError):
    """Monthly quota exhausted (status 402).

    Extra attributes read from the error payload:
        upgrade_url   — dashboard URL for upgrading
        calls_used    — calls consumed this month
        calls_limit   — limit of the current plan
        reset_date    — ISO date of the reset
        current_plan  — name of the current plan
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        err = self.payload.get("error") if isinstance(self.payload, dict) else None
        if isinstance(err, dict):
            self.upgrade_url = err.get("upgrade_url")
            self.calls_used = err.get("calls_used")
            self.calls_limit = err.get("calls_limit")
            self.reset_date = err.get("reset_date")
            self.current_plan = err.get("current_plan")
        else:
            self.upgrade_url = None
            self.calls_used = None
            self.calls_limit = None
            self.reset_date = None
            self.current_plan = None


class NotReady(MyOCRError):
    """Job result requested before status=done."""


class NotFound(MyOCRError):
    """Job/key not found."""


class OcrEngineError(MyOCRError):
    """Upstream OCR engine error (502)."""


class StorageError(MyOCRError):
    """Object storage error (R2)."""


class ServiceNotReady(MyOCRError):
    """Endpoint not active yet (503)."""


class RateLimited(MyOCRError):
    """Rate limit exceeded (429)."""


class InternalError(MyOCRError):
    """Generic server error (500)."""


# API error code → SDK exception mapping
CODE_TO_EXCEPTION = {
    "MISSING_API_KEY": MissingApiKey,
    "INVALID_API_KEY": InvalidApiKey,
    "UNSUPPORTED_MODEL": UnsupportedModel,
    "UNSUPPORTED_FILE_TYPE": UnsupportedFileType,
    "MISSING_FILE": MissingFile,
    "FILE_TOO_LARGE": FileTooLarge,
    "TOO_MANY_PAGES": TooManyPages,
    "INVALID_WEBHOOK_URL": InvalidWebhookUrl,
    "QUOTA_EXCEEDED": QuotaExceeded,
    "INSUFFICIENT_CREDITS": QuotaExceeded,
    "quota_exceeded": QuotaExceeded,
    "NOT_READY": NotReady,
    "NOT_FOUND": NotFound,
    "OCR_ERROR": OcrEngineError,
    "STORAGE_ERROR": StorageError,
    "SERVICE_NOT_READY": ServiceNotReady,
    "INTERNAL_ERROR": InternalError,
}


def from_response(status_code: int, body, request_id: Optional[str] = None) -> MyOCRError:
    """Build the appropriate exception from a non-2xx HTTP response."""
    code = None
    message = ""
    payload = None
    if isinstance(body, dict):
        payload = body
        err = body.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            message = err.get("message", "")
        elif isinstance(err, str):
            code = err
            message = body.get("message", "")
    elif isinstance(body, (bytes, str)):
        message = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body

    if status_code == 429:
        return RateLimited(message or "Rate limit exceeded", code=code or "RATE_LIMITED",
                           status_code=status_code, request_id=request_id, payload=payload)

    if code and code in CODE_TO_EXCEPTION:
        return CODE_TO_EXCEPTION[code](message or code, code=code,
                                       status_code=status_code, request_id=request_id, payload=payload)

    # Fallback for status codes without a structured body
    if status_code == 401:
        return InvalidApiKey(message or "Unauthorized", code=code, status_code=status_code,
                             request_id=request_id, payload=payload)
    if status_code == 404:
        return NotFound(message or "Not found", code=code, status_code=status_code,
                        request_id=request_id, payload=payload)
    if status_code == 402:
        return QuotaExceeded(message or "Quota exceeded", code=code, status_code=status_code,
                             request_id=request_id, payload=payload)
    if status_code >= 500:
        return InternalError(message or f"Server error ({status_code})", code=code,
                             status_code=status_code, request_id=request_id, payload=payload)

    return MyOCRError(message or f"HTTP {status_code}", code=code, status_code=status_code,
                      request_id=request_id, payload=payload)
