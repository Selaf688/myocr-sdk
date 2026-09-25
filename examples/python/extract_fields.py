"""Pick your own columns with model="fields".

fields_mode="page" (default) gives one row per page, which suits one document
per page (forms, delivery notes). fields_mode="list" gives one row per printed
item, which suits lists and statements.

    python extract_fields.py ../sample_bank_statement.pdf transactions.xlsx
"""
import sys

from myocr_client import MyOCRClient

src = sys.argv[1] if len(sys.argv) > 1 else "../sample_bank_statement.pdf"
dst = sys.argv[2] if len(sys.argv) > 2 else "fields.xlsx"

client = MyOCRClient()
result = client.convert(
    src,
    model="fields",
    fields=["Date", "Description", "Amount"],
    fields_mode="list",
    page_range="1",  # PDF only: '3', '3-5', '1,3-5', '2-'. Pages left out are not billed.
)
result.save(dst)
print(f"Saved {dst}")
