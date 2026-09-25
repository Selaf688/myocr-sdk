/**
 * myocr-client — Node.js / TypeScript SDK for myocr.app v1 API.
 *
 *     import { MyOCRClient } from 'myocr-client';
 *     const client = new MyOCRClient({ apiKey: 'sk_live_...' });
 *     const result = await client.convert('invoice.pdf', { model: 'invoice' });
 *     await result.save('out.xlsx');
 */
export { MyOCRClient } from './client.js';
export type {
  MyOCRClientOptions,
  ConvertOptions,
  CreateJobOptions,
  BatchOptions,
  ExtractionOptions,
  FileInput,
} from './client.js';

export {
  ConversionResult,
  Job,
  JobResult,
  BatchResult,
  JobStatus,
} from './models.js';

export type {
  ApiModel,
  FieldsMode,
  OutputFormat,
  JobData,
  BatchErrorEntry,
} from './models.js';

export {
  MyOCRError,
  MissingApiKey,
  InvalidApiKey,
  UnsupportedModel,
  UnsupportedFileType,
  MissingFile,
  FileTooLarge,
  TooManyPages,
  InvalidWebhookUrl,
  QuotaExceeded,
  NotReady,
  NotFound,
  OcrEngineError,
  StorageError,
  ServiceNotReady,
  RateLimited,
  InternalError,
  fromResponse,
} from './exceptions.js';

export { verifyWebhookSignature } from './webhook.js';
