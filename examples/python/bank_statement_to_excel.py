"""Convert a bank statement (PDF, scan or photo) to Excel.

The workbook has one sheet with the statement header, one with the transactions
and one with the balance check.

    pip install myocr-client
    export MYOCR_API_KEY=sk_test_...
    python bank_statement_to_excel.py ../sample_bank_statement.pdf statement.xlsx
"""
import sys

from myocr_client import MyOCRClient

src = sys.argv[1] if len(sys.argv) > 1 else "../sample_bank_statement.pdf"
dst = sys.argv[2] if len(sys.argv) > 2 else "statement.xlsx"

client = MyOCRClient()
result = client.convert(src, model="bank_statement")  # xlsx by default
result.save(dst)
print(f"Saved {dst} ({result.pages_used} page(s), request {result.request_id})")
