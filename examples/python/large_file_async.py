"""Large or multi-page documents: use an async job.

/v1/convert is synchronous and takes files up to 5 MB and 10 pages.
Jobs take up to 50 MB and 500 pages. Poll with job.wait(), or pass
webhook_url=... to be notified (see webhook_receiver.py).

    python large_file_async.py statement_2025.pdf statement_2025.xlsx
"""
import sys

from myocr_client import MyOCRClient

src = sys.argv[1] if len(sys.argv) > 1 else "../sample_bank_statement.pdf"
dst = sys.argv[2] if len(sys.argv) > 2 else "statement.xlsx"

client = MyOCRClient()
job = client.create_job(src, model="bank_statement")
print(f"Job {job.request_id} queued")

job.wait(timeout=900)  # polls with exponential backoff
if job.is_done:
    job.download(dst)
    print(f"Saved {dst}")
else:
    print(f"Job ended with status {job.status}: {job.error_detail}")
    sys.exit(1)
