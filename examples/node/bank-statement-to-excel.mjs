// Convert a bank statement (PDF, scan or photo) to Excel.
//
//   npm install myocr-client
//   export MYOCR_API_KEY=sk_test_...
//   node bank-statement-to-excel.mjs ../sample_bank_statement.pdf statement.xlsx
import { MyOCRClient } from 'myocr-client';

const [src = '../sample_bank_statement.pdf', dst = 'statement.xlsx'] = process.argv.slice(2);
const client = new MyOCRClient();

const result = await client.convert(src, { model: 'bank_statement' }); // xlsx by default
await result.save(dst);
console.log(`Saved ${dst} (${result.pagesUsed} page(s), request ${result.requestId})`);
