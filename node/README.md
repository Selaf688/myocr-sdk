# myocr-client — Node.js / TypeScript SDK for myocr.app

Official Node.js client for the **[myocr.app](https://www.myocr.app)** API. Convert PDFs, scans and photos to structured Excel or JSON: bank statements (with a balance check), invoices, receipts, business cards, generic tables, plain text, or the columns you choose. Zero runtime dependencies (Node 18+ native fetch/FormData/crypto).

Source, issues and runnable examples: **[github.com/Selaf688/myocr-sdk](https://github.com/Selaf688/myocr-sdk)**.

[![npm version](https://img.shields.io/npm/v/myocr-client.svg)](https://www.npmjs.com/package/myocr-client)
[![Node](https://img.shields.io/node/v/myocr-client.svg)](https://www.npmjs.com/package/myocr-client)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![TypeScript](https://img.shields.io/badge/TypeScript-strict-blue.svg)](https://www.typescriptlang.org/)

---

## Install

```bash
npm install myocr-client
# or yarn add myocr-client / pnpm add myocr-client
```

## Quick start

Create an account, then get a key from the [API dashboard](https://www.myocr.app/account/api). A **sandbox key** (`sk_test_...`) needs no card and includes 5 pages on the synchronous endpoint, enough to try everything below. Then:

```typescript
import { MyOCRClient } from 'myocr-client';

const client = new MyOCRClient({ apiKey: 'sk_live_...' });
// or set MYOCR_API_KEY env var

// Synchronous conversion (≤5MB, ≤10 pages, returns immediately)
const result = await client.convert('invoice.pdf', { model: 'invoice' });
await result.save('invoice.xlsx');

console.log(result.pagesUsed, result.model, result.requestId);
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

With `output: 'json'`, a bank statement comes back with a `reconciliation` block: opening balance + credits - debits, compared with the closing balance printed on the statement.

```typescript
const result = await client.convert('statement.pdf', { model: 'bank_statement', output: 'json' });
const check = result.data.reconciliation;
// { ok: true, opening: 2450, credits: 2845.75, debits: 1247.07,
//   computed_closing: 4048.68, closing: 4048.68, delta: 0, n_transactions: 10, ... }
if (!check.ok) console.log(`Off by ${check.delta}: check the statement before importing`);
```

The xlsx output carries the same check in its `balance check` sheet.

## Only some pages

`pageRange` (PDF only) converts just the pages you list: `'3'`, `'3-5'`, `'1,3-5'`, `'2-'` (to the end). Pages outside the range are not billed. It works on `convert()`, `createJob()` and `batch()` (where it applies to every file).

```typescript
const result = await client.convert('invoice_with_attachments.pdf', { model: 'invoice', pageRange: '1' });
```

## Your own columns

```typescript
const result = await client.convert('delivery_notes.pdf', {
  model: 'fields',
  fields: ['Date', 'Delivery note number', 'Customer', 'Total'], // max 60
  fieldsMode: 'page', // one row per page; 'list' = one row per printed item
});
await result.save('delivery_notes.xlsx');
```

## Async jobs (files > 5MB or > 10 pages)

```typescript
const job = await client.createJob('annual_report.pdf', {
  model: 'bank_statement',
  webhookUrl: 'https://your.app/webhooks/myocr', // optional
});

// Option 1: polling with exponential backoff
await job.wait({ timeoutMs: 600_000 });
await job.download('report.xlsx');

// Option 2: notified via webhook — see "Webhook verification" below
```

## Batch (1–20 files in one call)

```typescript
const batch = await client.batch(
  ['a.pdf', 'b.pdf', 'c.pdf'],
  {
    model: 'invoice',
    webhookUrl: 'https://your.app/webhooks/myocr',
  },
);
console.log(`${batch.jobsCreated} jobs queued; ${batch.errors.length} errors`);

// Wait for all and download
const done = await batch.waitAll({ timeoutMs: 1_200_000 });
for (const job of done) {
  if (job.isDone) {
    await job.download(`out/${job.requestId}.xlsx`);
  }
}
```

## Webhooks

Pass `webhookUrl` to `createJob()` or `batch()` and myocr POSTs a JSON notification when each job ends:

```json
{"event": "job.completed", "data": {"request_id": "...", "status": "done", "model": "bank_statement", "pages_used": 3}}
```

Events: `job.completed`, `job.failed`. Failed deliveries are retried after 1m, 5m, 30m and 2h.

Treat the notification as a signal, not as proof: before acting on it, confirm the job with your own key. The API is the source of truth, so a forged request cannot make you download or trust anything.

```typescript
import express from 'express';
import { MyOCRClient } from 'myocr-client';

const app = express();
const client = new MyOCRClient();

app.post('/webhooks/myocr', express.json(), async (req, res) => {
  const requestId = req.body?.data?.request_id;
  if (requestId) {
    const job = await client.getJob(requestId); // authenticated with your key
    if (job.isDone) await job.download(`${requestId}.xlsx`);
  }
  res.status(204).end();
});
```

Deliveries also carry an `X-MyOCR-Signature: sha256=<hex>` header (HMAC-SHA256 of the raw body). The SDK includes `verifyWebhookSignature(body, signature, secret)` to check it against a signing secret.

## Error handling

Every API error code maps to a typed exception:

```typescript
import { MyOCRClient, QuotaExceeded, InvalidApiKey, OcrEngineError } from 'myocr-client';

const client = new MyOCRClient({ apiKey: 'sk_live_...' });

try {
  const result = await client.convert('doc.pdf', { model: 'invoice' });
} catch (e) {
  if (e instanceof QuotaExceeded) {
    console.log(`Plan ${e.currentPlan}, used ${e.callsUsed}/${e.callsLimit}`);
    console.log(`Upgrade: ${e.upgradeUrl}`);
    console.log(`Resets: ${e.resetDate}`);
  } else if (e instanceof InvalidApiKey) {
    console.log('Rotate your key from /account/api');
  } else if (e instanceof OcrEngineError) {
    console.log('OCR engine upstream failure; safe to retry');
  } else {
    throw e;
  }
}
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

The SDK automatically retries `429` and `5xx` responses up to 3 times with exponential backoff (honoring `Retry-After` when present).

## Input flexibility

`convert()`, `createJob()`, and `batch()` accept:

- A file path: `client.convert('/path/to/doc.pdf', ...)`
- A Buffer: `client.convert(Buffer.from(...), { filename: 'doc.pdf', ... })`
- A `Uint8Array`
- A `Blob`
- An object `{ data: Buffer | Blob, filename?: string }`

## Configuration

| Option | Env var | Default |
|---|---|---|
| `apiKey` | `MYOCR_API_KEY` | — (required) |
| `baseUrl` | `MYOCR_BASE_URL` | `https://api.myocr.app` |
| `timeoutMs` | — | 60000 |
| `retryAttempts` | — | 3 |
| `fetchImpl` | — | global `fetch` |

For staging:

```typescript
const client = new MyOCRClient({
  apiKey: 'sk_test_...',
  baseUrl: 'https://beta.myocr.app',
});
```

For custom fetch (e.g. with proxy, `undici` agent):

```typescript
import { fetch } from 'undici';
const client = new MyOCRClient({ apiKey: '...', fetchImpl: fetch as typeof globalThis.fetch });
```

## Monitor your quota

Check current month usage programmatically (e.g. to upgrade before exhaustion):

```typescript
const usage = await client.usage();
// {
//   plan: 'api_starter', calls_used: 420, calls_limit: 2500,
//   percentage: 16.8, reset_date: '2026-11-01T00:00:00',
//   year_month: '2026-10', is_test_key: false
// }
if (usage.percentage && (usage.percentage as number) > 80) {
  // alert ops, upgrade plan, or stop background workers
}
```

## Status & limits

```typescript
const status = await client.status();
// service, version, models_supported, features, limits
```

## Rate limits (server-side)

| Endpoint | Limit |
|---|---|
| `POST /v1/convert` | 60 / min |
| `POST /v1/jobs` | 120 / min |
| `POST /v1/batch` | 30 / min |

The SDK handles `429` with automatic retry. If you saturate the quota, upgrade your plan from the dashboard.

## TypeScript

The package ships type declarations (`.d.ts`) — full IntelliSense out of the box. All public surface is strict-typed.

## Compatibility

- **Node.js 18+** (uses native `fetch`, `FormData`, `Blob`, `node:crypto`)
- **Browser**: pass the file as `Blob` / `File` (e.g. from `<input type="file">`) — no Node-specific APIs are required for `convert()` / `createJob()`. Note: webhook verification (`verifyWebhookSignature`) requires `node:crypto` so it runs server-side only.
- **Serverless**: works in AWS Lambda (Node 18+ runtime), Cloud Functions, Vercel, Cloudflare Workers (use Workers' native fetch).

## Reference

- **Full OpenAPI spec:** [openapi.json](https://www.myocr.app/docs/api/openapi.json) (import it into Postman or Insomnia)
- **Interactive docs:** [/docs/api](https://www.myocr.app/docs/api) (Scalar UI)
- **Dashboard:** [/account/api](https://www.myocr.app/account/api) — manage keys, view usage, upgrade
- **Python SDK** (same surface): [pypi.org/project/myocr-client](https://pypi.org/project/myocr-client/)

## Development

```bash
git clone https://github.com/Selaf688/myocr-sdk
cd myocr-sdk/node
npm install
npm test
npm run build           # tsc → dist/
npm run typecheck
```

## Versioning

Semantic versioning. The API itself is `v1` and stable; the SDK can release patch/minor independently.

## License

MIT. See [LICENSE](./LICENSE).

## Support

- Documentation: <https://www.myocr.app/docs/api>
- Email: info@myocr.app
- Issues: <https://github.com/Selaf688/myocr-sdk/issues>
