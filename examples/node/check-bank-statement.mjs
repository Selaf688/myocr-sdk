// Check that a bank statement balances before you import it.
//
//   npm install myocr-client
//   export MYOCR_API_KEY=sk_test_...
//   node check-bank-statement.mjs ../sample_bank_statement.pdf
import { MyOCRClient } from 'myocr-client';

const path = process.argv[2] ?? '../sample_bank_statement.pdf';
const client = new MyOCRClient(); // reads MYOCR_API_KEY

const result = await client.convert(path, { model: 'bank_statement', output: 'json' });
const statement = result.data.bank_statement;
const check = result.data.reconciliation;

console.log(`${statement.bank_name} - ${statement.period} (${statement.currency})`);
console.log(`Transactions read: ${check.n_transactions}`);
console.log(`Opening ${check.opening.toFixed(2)} + credits ${check.credits.toFixed(2)} - debits ${check.debits.toFixed(2)} = ${check.computed_closing.toFixed(2)}`);
console.log(`Closing balance on the statement: ${check.closing.toFixed(2)}`);

if (check.ok) {
  console.log('CONSISTENT: safe to import.');
} else {
  console.log(`NOT CONSISTENT: off by ${check.delta.toFixed(2)}. Check the statement before importing.`);
  process.exitCode = 1;
}
