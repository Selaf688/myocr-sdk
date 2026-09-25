# myocr SDKs

Official client libraries for the [myocr.app](https://www.myocr.app) API: turn PDFs, scans and photos of bank statements, invoices, receipts and tables into Excel or JSON.

| | Install | Docs |
|---|---|---|
| **Python** 3.8+ | `pip install myocr-client` | [python/](python) · [PyPI](https://pypi.org/project/myocr-client/) |
| **Node.js** 18+ / TypeScript | `npm install myocr-client` | [node/](node) · [npm](https://www.npmjs.com/package/myocr-client) |
| **Any language** (HTTP) | — | [cURL examples](examples/curl) |

## Try it in two minutes

1. Create an account at [myocr.app](https://www.myocr.app/register_free) and a **sandbox key** in the [API dashboard](https://www.myocr.app/account/api). It needs no card and includes 5 pages on the synchronous endpoint.
2. Run the balance check on the fictitious statement in [`examples/`](examples):

```bash
pip install myocr-client
export MYOCR_API_KEY=sk_test_...
cd examples/python
python check_bank_statement.py ../sample_bank_statement.pdf
```

```
Example Bank - 01 Sep 2026 - 30 Sep 2026 (GBP)
Transactions read: 10
Opening 2450.00 + credits 2845.75 - debits 1247.07 = 4048.68
Closing balance on the statement: 4048.68
CONSISTENT: safe to import.
```

## What the API does

- **Models:** `bank_statement` (header, transactions and a balance check), `invoice`, `receipt`, `business_card`, `tables`, `text`, and `fields` for the columns you choose.
- **Balance check on bank statements:** opening balance + credits - debits compared with the closing balance printed on the statement, returned as a `reconciliation` block in JSON and as a sheet in Excel.
- **Sync** `POST /v1/convert` for files up to 5 MB and 10 pages; **async** `POST /v1/jobs` up to 50 MB and 500 pages, with polling or webhooks; **batch** `POST /v1/batch` for up to 20 files per call.
- **`page_range`** converts only the pages you need; pages left out are not billed.
- Output as `xlsx`, `json` or `txt`.

## Examples

| | Python | Node.js |
|---|---|---|
| Check that a statement balances | [check_bank_statement.py](examples/python/check_bank_statement.py) | [check-bank-statement.mjs](examples/node/check-bank-statement.mjs) |
| Bank statement to Excel | [bank_statement_to_excel.py](examples/python/bank_statement_to_excel.py) | [bank-statement-to-excel.mjs](examples/node/bank-statement-to-excel.mjs) |
| Large files (async job) | [large_file_async.py](examples/python/large_file_async.py) | [large-file-async.mjs](examples/node/large-file-async.mjs) |
| A whole folder (batch) | [batch_folder.py](examples/python/batch_folder.py) | |
| Your own columns | [extract_fields.py](examples/python/extract_fields.py) | |
| Webhook receiver | [webhook_receiver.py](examples/python/webhook_receiver.py) | |

## Documentation

- API reference: <https://www.myocr.app/docs/api>
- OpenAPI spec (import into Postman or Insomnia): <https://www.myocr.app/docs/api/openapi.json>
- Plans and pricing: <https://www.myocr.app/api>
- Service status: <https://status.myocr.app>

## Support

Open an [issue](https://github.com/Selaf688/myocr-sdk/issues) or write to info@myocr.app.

## License

MIT © MAD.AI SRL. The SDKs are open source; the myocr.app service they connect to is a paid API with a free sandbox.
