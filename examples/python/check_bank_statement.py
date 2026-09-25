"""Check that a bank statement balances before you import it.

myocr reads the statement and runs one arithmetic check:
opening balance + credits - debits must equal the closing balance printed on it.

    pip install myocr-client
    export MYOCR_API_KEY=sk_test_...
    python check_bank_statement.py ../sample_bank_statement.pdf
"""
import sys

from myocr_client import MyOCRClient

path = sys.argv[1] if len(sys.argv) > 1 else "../sample_bank_statement.pdf"
client = MyOCRClient()  # reads MYOCR_API_KEY

result = client.convert(path, model="bank_statement", output="json")
statement = result.data["bank_statement"]
check = result.data["reconciliation"]

print(f"{statement['bank_name']} - {statement['period']} ({statement['currency']})")
print(f"Transactions read: {check['n_transactions']}")
print(f"Opening {check['opening']:.2f} + credits {check['credits']:.2f} "
      f"- debits {check['debits']:.2f} = {check['computed_closing']:.2f}")
print(f"Closing balance on the statement: {check['closing']:.2f}")

if check["ok"]:
    print("CONSISTENT: safe to import.")
else:
    print(f"NOT CONSISTENT: off by {check['delta']:.2f}. Check the statement before importing.")
    sys.exit(1)
