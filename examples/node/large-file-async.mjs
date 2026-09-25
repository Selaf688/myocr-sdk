// Large or multi-page documents: use an async job (up to 50 MB and 500 pages).
// Poll with job.wait(), or pass webhookUrl to be notified.
//
//   node large-file-async.mjs statement_2025.pdf statement_2025.xlsx
import { MyOCRClient } from 'myocr-client';

const [src = '../sample_bank_statement.pdf', dst = 'statement.xlsx'] = process.argv.slice(2);
const client = new MyOCRClient();

const job = await client.createJob(src, { model: 'bank_statement' });
console.log(`Job ${job.requestId} queued`);

await job.wait({ timeoutMs: 15 * 60 * 1000 }); // polls with exponential backoff
if (job.isDone) {
  await job.download(dst);
  console.log(`Saved ${dst}`);
} else {
  console.log(`Job ended with status ${job.status}: ${job.errorDetail}`);
  process.exitCode = 1;
}
