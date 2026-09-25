# cURL

Every endpoint takes your key in the `X-API-Key` header. Base URL: `https://api.myocr.app`.

```bash
export MYOCR_API_KEY=sk_test_...
```

## Convert (synchronous, up to 5 MB and 10 pages)

```bash
# Bank statement to Excel
curl -sS https://api.myocr.app/v1/convert \
  -H "X-API-Key: $MYOCR_API_KEY" \
  -F file=@../sample_bank_statement.pdf \
  -F model=bank_statement \
  -o statement.xlsx

# Same statement as JSON, with the balance check in "reconciliation"
curl -sS https://api.myocr.app/v1/convert \
  -H "X-API-Key: $MYOCR_API_KEY" \
  -F file=@../sample_bank_statement.pdf \
  -F model=bank_statement \
  -F output=json

# Only some pages (PDF only; pages left out are not billed)
curl -sS https://api.myocr.app/v1/convert \
  -H "X-API-Key: $MYOCR_API_KEY" \
  -F file=@invoice_with_attachments.pdf \
  -F model=invoice \
  -F page_range=1 \
  -o invoice.xlsx

# Your own columns
curl -sS https://api.myocr.app/v1/convert \
  -H "X-API-Key: $MYOCR_API_KEY" \
  -F file=@../sample_bank_statement.pdf \
  -F model=fields \
  -F "fields=Date,Description,Amount" \
  -F fields_mode=list \
  -o fields.xlsx
```

## Async job (up to 50 MB and 500 pages)

```bash
# 1. Create the job (add -F webhook_url=https://your.app/webhooks/myocr to be notified)
curl -sS https://api.myocr.app/v1/jobs \
  -H "X-API-Key: $MYOCR_API_KEY" \
  -F file=@../sample_bank_statement.pdf \
  -F model=bank_statement
# -> {"success": true, "data": {"request_id": "abc123", "status": "pending", ...}}

# 2. Check its status until it is "done" (or "failed")
curl -sS https://api.myocr.app/v1/jobs/abc123 -H "X-API-Key: $MYOCR_API_KEY"

# 3. Get a temporary download link for the result...
curl -sS https://api.myocr.app/v1/jobs/abc123/result -H "X-API-Key: $MYOCR_API_KEY"
# -> {"success": true, "data": {"result_url": "https://...", "expires_in": 86400}}

# ...and download it (no API key needed on the link). With jq, in one line:
curl -sS https://api.myocr.app/v1/jobs/abc123/result -H "X-API-Key: $MYOCR_API_KEY" \
  | jq -r .data.result_url | xargs curl -sS -o statement.xlsx
```

## Quota

```bash
curl -sS https://api.myocr.app/v1/usage -H "X-API-Key: $MYOCR_API_KEY"
```

Full reference: <https://www.myocr.app/docs/api> · OpenAPI: <https://www.myocr.app/docs/api/openapi.json>
