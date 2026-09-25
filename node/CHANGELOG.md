# Changelog

All notable changes to `myocr-client` (Node.js / TypeScript) will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-09-25

### Added
- `pageRange`, `fields` and `fieldsMode` options on `convert()`, `createJob()` and
  `batch()`, the `fields` model and the `FieldsMode` / `ExtractionOptions` types.
- `Job.filename` on jobs created by `batch()`.

### Changed
- The `User-Agent` header reports the real SDK version (it was fixed at 0.1.0).
- Package links point to the public repository <https://github.com/Selaf688/myocr-sdk>.

## [0.2.0] — 2026-08-16

### Added
- `rotateKey()` and `listJobs()`.

 — 2026-05-26 (initial)

### Added
- `MyOCRClient` class with all v1 endpoints:
  - `convert()` — sync conversion (xlsx / txt / json output)
  - `createJob()` / `getJob()` / `getJobResult()` / `deleteJob()` — async lifecycle
  - `batch()` — 1–20 files per call
  - `status()` / `usage()` — health check + quota
  - `listKeys()` — administrative
- `Job` model with `wait()` polling (exponential backoff), `download()`, `delete()`.
- `JobStatus` enum (`Pending`, `Processing`, `Done`, `Failed`).
- `ConversionResult` / `JobResult` / `BatchResult` typed wrappers.
- 16 typed exception classes mapped 1:1 to API error codes (`QuotaExceeded`, `InvalidApiKey`, `OcrEngineError`, ...).
- `verifyWebhookSignature()` helper for HMAC-SHA256 validation of incoming webhooks.
- Automatic retry on 429 / 5xx with exponential backoff (honors `Retry-After`).
- Accepts file path, Buffer, Uint8Array, Blob, or `{ data, filename }` object.
- Env var fallback `MYOCR_API_KEY`, `MYOCR_BASE_URL`.
- Full Vitest suite (27 tests) using mocked fetch.
- Zero runtime dependencies (Node 18+ native fetch/FormData/Blob/crypto).
- TypeScript strict mode + shipped `.d.ts` declarations.
