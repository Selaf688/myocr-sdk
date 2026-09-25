# Changelog

All notable changes to `myocr-client` will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-09-25

### Added
- `page_range`, `fields` and `fields_mode` on `convert()`, `create_job()` and `batch()`,
  and the `fields` model (your own columns).
- `Job.filename` on jobs created by `batch()`, so results can be matched to files even
  when some files are rejected.

### Changed
- The `User-Agent` header reports the real SDK version (it was fixed at 0.1.0).
- Docstrings in English. Project links point to the public repository
  <https://github.com/Selaf688/myocr-sdk>.

## [0.2.0] — 2026-08-16

### Changed (BREAKING)
- `AzureError` renamed to `OcrEngineError`, error code `AZURE_ERROR` to `OCR_ERROR`.

### Added
- `client.usage()`: current quota for your key (`GET /v1/usage`).
- `client.rotate_key()` and `client.list_jobs()`.
- `BatchResult.wait_all()` polls jobs in parallel.

## [0.1.0] — 2026-05-25 (initial)

### Added
- `MyOCRClient` class with all v1 endpoints:
  - `convert()` — sync conversion (xlsx / txt / json output)
  - `create_job()` / `get_job()` / `get_job_result()` / `delete_job()` — async lifecycle
  - `batch()` — 1–20 files per call
  - `status()` — public health check
  - `list_keys()` — administrative
- `Job` model with `wait()` polling (exponential backoff), `download()`, `delete()`.
- `JobStatus` enum (`pending`, `processing`, `done`, `failed`).
- `ConversionResult` / `JobResult` / `BatchResult` typed wrappers.
- 16 typed exceptions mapped 1:1 to API error codes (`QuotaExceeded`, `InvalidApiKey`, `OcrEngineError`, ...).
- `verify_webhook_signature()` helper for HMAC-SHA256 validation of incoming webhooks.
- Automatic retry on 429 / 5xx with exponential backoff (honors `Retry-After`).
- Accepts file path, bytes, or file-like input.
- Env var fallback `MYOCR_API_KEY`, `MYOCR_BASE_URL`.
- Full pytest suite with `responses` library mocking.
