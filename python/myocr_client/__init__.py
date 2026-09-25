"""myocr.app — Python SDK for the v1 API.

    from myocr_client import MyOCRClient
    client = MyOCRClient(api_key="sk_live_...")
    result = client.convert("invoice.pdf", model="invoice")
    result.save("out.xlsx")

Async jobs (large files):
    job = client.create_job("big.pdf", model="bank_statement",
                            webhook_url="https://my.app/webhook")
    job.wait()  # polls with exponential backoff
    job.download("out.xlsx")
"""
from .client import MyOCRClient
from .models import ConversionResult, Job, JobStatus, JobResult, BatchResult
from .exceptions import (
    MyOCRError,
    MissingApiKey,
    InvalidApiKey,
    UnsupportedModel,
    UnsupportedFileType,
    MissingFile,
    FileTooLarge,
    TooManyPages,
    InvalidWebhookUrl,
    QuotaExceeded,
    NotReady,
    NotFound,
    OcrEngineError,
    StorageError,
    ServiceNotReady,
    RateLimited,
    InternalError,
)
from .webhook import verify_webhook_signature

from ._version import __version__
__all__ = [
    "MyOCRClient",
    "ConversionResult",
    "Job",
    "JobStatus",
    "JobResult",
    "BatchResult",
    "MyOCRError",
    "MissingApiKey",
    "InvalidApiKey",
    "UnsupportedModel",
    "UnsupportedFileType",
    "MissingFile",
    "FileTooLarge",
    "TooManyPages",
    "InvalidWebhookUrl",
    "QuotaExceeded",
    "NotReady",
    "NotFound",
    "OcrEngineError",
    "StorageError",
    "ServiceNotReady",
    "RateLimited",
    "InternalError",
    "verify_webhook_signature",
]
