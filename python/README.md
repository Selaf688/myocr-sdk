# myocr-client — Python SDK for myocr.app

Official Python client for the **[myocr.app](https://www.myocr.app)** API. Convert PDFs, scans and photos to structured Excel or JSON: bank statements (with a balance check), invoices, receipts, business cards, generic tables, plain text, or the columns you choose.

Source, issues and runnable examples: **[github.com/Selaf688/myocr-sdk](https://github.com/Selaf688/myocr-sdk)**.

[![PyPI version](https://img.shields.io/pypi/v/myocr-client.svg)](https://pypi.org/project/myocr-client/)
[![Python versions](https://img.shields.io/pypi/pyversions/myocr-client.svg)](https://pypi.org/project/myocr-client/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Install

```bash
pip install myocr-client
```

## Quick start

Create an account, then get a key from the [API dashboard](https://www.myocr.app/account/api). A **sandbox key** (`sk_test_...`) needs no card and includes 5 pages on the synchronous endpoint, enough to try everything below. Then:

```python
from myocr_client import MyOCRClient

client = MyOCRClient(api_key="sk_live_...")
# or set MYOCR_API_KEY in env

# Synchronous conversion (≤5MB, ≤10 pages, returns immediately)
result = client.convert("invoice.pdf", model="invoice")
result.save("invoice.xlsx")

print(result.pages_used, result.model, result.request_id)
```

## Models

| Model | Output | Best for |
|---|---|---|
| `tables` | xlsx with generic tables | Any structured table |
| `text` | plain txt | OCR text extraction |
| `invoice` | xlsx with Vendor / Customer / Total / Line items | Invoices, bills |
| `receipt` | xlsx with Merchant / Date / Items / Total | Receipts |
| `bank_statement` | xlsx with Account / Transactions sheet | Bank statements |
| `business_card` | xlsx with Contact / Company / Phones / Emails | Business cards |
| `fields` | xlsx with the columns you name in `fields` | Forms, delivery notes, any document where you know what you want |

## Check that a bank statement balances

With `output="json"`, a bank statement comes back with a `reconciliation` block: opening balance + credits - debits, compared with the closing balance printed on the statement.

```python
result = client.convert("statement.pdf", model="bank_statement", output="json")
check = result.data["reconciliation"]
# {'ok': True, 'opening': 2450.0, 'credits': 2845.75, 'debits': 1247.07,
#  'computed_closing': 4048.68, 'closing': 4048.68, 'delta': 0.0, 'n_transactions': 10, ...}
if not check["ok"]:
    print(f"Off by {check['delta']:.2f}: check the statement before importing")
```

The xlsx output carries the same check in its `balance check` sheet.

## Only some pages

`page_range` (PDF only) converts just the pages you list: `"3"`, `"3-5"`, `"1,3-5"`, `"2-"` (to the end). Pages outside the range are not billed. It works on `convert()`, `create_job()` and `batch()` (where it applies to every file).

```python
result = client.convert("invoice_with_attachments.pdf", model="invoice", page_range="1")
```

## Your own columns

```python
result = client.convert(
    "delivery_notes.pdf",
    model="fields",
    fields=["Date", "Delivery note number", "Customer", "Total"],  # max 60
    fields_mode="page",  # one row per page; "list" = one row per printed item
)
result.save("delivery_notes.xlsx")
```

## Async jobs (files > 5MB or > 10 pages)

```python
job = client.create_job(
    "annual_report.pdf",
    model="bank_statement",
    webhook_url="https://your.app/webhooks/myocr",  # optional
)

# Option 1: polling with exponential backoff
job.wait(timeout=600)
job.download("report.xlsx")

# Option 2: notified via webhook (preferred for prod) — see "Webhook verification" below
```

## Batch (1–20 files in one call)

```python
result = client.batch(
    ["a.pdf", "b.pdf", "c.pdf"],
    model="invoice",
    webhook_url="https://your.app/webhooks/myocr",
)
print(result.jobs_created, "jobs queued;", len(result.errors), "errors")

# Wait for all and download
for job in result.wait_all(timeout=1200):
    if job.is_done:
        job.download(f"{job.request_id}.xlsx")
```

## Webhooks

Pass `webhook_url=` to `create_job()` or `batch()` and myocr POSTs a JSON notification when each job ends:

```json
{"event": "job.completed", "data": {"request_id": "...", "status": "done", "model": "bank_statement", "pages_used": 3}}
```

Events: `job.completed`, `job.failed`. Failed deliveries are retried after 1m, 5m, 30m and 2h.

Treat the notification as a signal, not as proof: before acting on it, confirm the job with your own key. The API is the source of truth, so a forged request cannot make you download or trust anything.

```python
from flask import Flask, request
from myocr_client import MyOCRClient

app = Flask(__name__)
client = MyOCRClient()

@app.post("/webhooks/myocr")
def myocr_webhook():
    event = request.get_json(silent=True) or {}
    request_id = (event.get("data") or {}).get("request_id")
    if request_id:
        job = client.get_job(request_id)  # authenticated with your key
        if job.is_done:
            job.download(f"{request_id}.xlsx")
    return "", 204
```

Deliveries also carry an `X-MyOCR-Signature: sha256=<hex>` header (HMAC-SHA256 of the raw body). The SDK includes `verify_webhook_signature(body, signature, secret)` to check it against a signing secret.

## Error handling

Every error code maps to a typed exception:

```python
from myocr_client import MyOCRClient, QuotaExceeded, InvalidApiKey, OcrEngineError

client = MyOCRClient(api_key="sk_live_...")

try:
    result = client.convert("doc.pdf", model="invoice")
except QuotaExceeded as e:
    print(f"Plan {e.current_plan}, used {e.calls_used}/{e.calls_limit}")
    print(f"Upgrade: {e.upgrade_url}")
    print(f"Resets: {e.reset_date}")
except InvalidApiKey:
    print("Rotate your key from /account/api")
except OcrEngineError:
    print("OCR engine upstream failure; safe to retry")
```

| Exception | HTTP | Code |
|---|---|---|
| `MissingApiKey` | 401 | `MISSING_API_KEY` |
| `InvalidApiKey` | 401 | `INVALID_API_KEY` |
| `UnsupportedModel` | 400 | `UNSUPPORTED_MODEL` |
| `UnsupportedFileType` | 400 | `UNSUPPORTED_FILE_TYPE` |
| `MissingFile` | 400 | `MISSING_FILE` |
| `FileTooLarge` | 413 | `FILE_TOO_LARGE` |
| `TooManyPages` | 413 | `TOO_MANY_PAGES` |
| `InvalidWebhookUrl` | 400 | `INVALID_WEBHOOK_URL` |
| `QuotaExceeded` | 402 | `QUOTA_EXCEEDED` |
| `NotReady` | 409 | `NOT_READY` |
| `NotFound` | 404 | `NOT_FOUND` |
| `OcrEngineError` | 502 | `OCR_ERROR` |
| `StorageError` | 503 | `STORAGE_ERROR` |
| `RateLimited` | 429 | — |
| `ServiceNotReady` | 503 | `SERVICE_NOT_READY` |
| `InternalError` | 500 | `INTERNAL_ERROR` |

The SDK automatically retries `429` and `5xx` responses up to 3 times with exponential backoff (honoring `Retry-After` when present). After retries exhausted the exception is raised.

## Input flexibility

`client.convert()` and `client.create_job()` accept:

- A file path: `client.convert("/path/to/doc.pdf", ...)`
- Raw bytes: `client.convert(pdf_bytes, filename="doc.pdf", ...)`
- A file-like object: `with open("doc.pdf", "rb") as f: client.convert(f, ...)`

## Configuration

| Argument | Env var | Default |
|---|---|---|
| `api_key` | `MYOCR_API_KEY` | — (required) |
| `base_url` | `MYOCR_BASE_URL` | `https://api.myocr.app` |
| `timeout` | — | 60s |
| `retry_attempts` | — | 3 |
| `session` | — | new `requests.Session()` |

For staging:

```python
client = MyOCRClient(api_key="sk_test_...", base_url="https://beta.myocr.app")
```

## Monitor your quota

Check current month usage programmatically (e.g. to upgrade before exhaustion):

```python
usage = client.usage()
# {
#   "plan": "api_starter", "calls_used": 420, "calls_limit": 2500,
#   "percentage": 16.8, "reset_date": "2026-11-01T00:00:00",
#   "year_month": "2026-10", "is_test_key": False
# }
if usage["percentage"] and usage["percentage"] > 80:
    # alert ops, upgrade plan, or stop background workers
    ...
```

## Status & limits

```python
status = client.status()
# {
#   "service": "myocr.app API", "version": "v1",
#   "models_supported": ["bank_statement", "business_card", ...],
#   "features": {"sync_convert": True, "async_jobs": True, "webhook": True, ...},
#   "limits": {"sync_max_bytes": 5242880, "sync_max_pages": 10,
#              "jobs_max_bytes": 52428800, "sync_rate_per_minute": 60,
#              "jobs_rate_per_minute": 120}
# }
```

## Rate limits (server-side)

| Endpoint | Limit |
|---|---|
| `POST /v1/convert` | 60 / min |
| `POST /v1/jobs` | 120 / min |
| `POST /v1/batch` | 30 / min |

The SDK handles `429` with automatic retry. If you saturate the quota, upgrade your plan from the dashboard.

## Reference

- **Full OpenAPI spec:** [openapi.json](https://www.myocr.app/docs/api/openapi.json) (import it into Postman or Insomnia)
- **Interactive docs:** [/docs/api](https://www.myocr.app/docs/api) (Scalar UI)
- **Dashboard:** [/account/api](https://www.myocr.app/account/api) — manage keys, view usage, upgrade
- **Webhook signing secret:** generated when you create a webhook integration; shared via dashboard.

## Development

```bash
git clone https://github.com/Selaf688/myocr-sdk
cd myocr-sdk/python
pip install -e ".[dev]"
pytest -v
```

Runnable examples, with a fictitious sample statement, are in [`examples/`](https://github.com/Selaf688/myocr-sdk/tree/main/examples).

## Versioning

Semantic versioning. The API itself is `v1` and stable; the SDK can release patch/minor independently.

## License

MIT. See [LICENSE](./LICENSE).

## Support

- Documentation: <https://www.myocr.app/docs/api>
- Email: info@myocr.app
- Issues: <https://github.com/Selaf688/myocr-sdk/issues>
