/**
 * Main client for the myocr.app v1 API.
 *
 * All methods throw subclasses of MyOCRError on API error codes.
 * Automatic retry on 429 and 5xx (3 attempts, exponential backoff 1s/2s/4s),
 * honoring Retry-After when present.
 *
 * Zero runtime dependencies — uses Node 18+ native fetch/FormData/crypto.
 */
import { promises as fs } from 'node:fs';
import { basename } from 'node:path';
import {
  ConversionResult,
  Job,
  JobResult,
  JobStatus,
  BatchResult,
  type ApiModel,
  type FieldsMode,
  type OutputFormat,
  type JobData,
} from './models.js';
import { MissingApiKey, InternalError, fromResponse } from './exceptions.js';

const DEFAULT_BASE_URL = 'https://api.myocr.app';
const DEFAULT_TIMEOUT_MS = 60_000;
const DEFAULT_RETRY_ATTEMPTS = 3;
const RETRYABLE_STATUS = new Set([429, 500, 502, 503, 504]);
const SDK_VERSION = '0.3.0';

export type FileInput =
  | string // path
  | Buffer
  | Uint8Array
  | Blob
  | { data: Buffer | Uint8Array | Blob; filename?: string };

export interface MyOCRClientOptions {
  apiKey?: string;
  baseUrl?: string;
  timeoutMs?: number;
  retryAttempts?: number;
  fetchImpl?: typeof fetch;
}

/** Options shared by convert(), createJob() and batch(). */
export interface ExtractionOptions {
  /**
   * PDF only. Convert just these pages: '3', '3-5', '1,3-5' or '2-' (to the end).
   * Pages outside the range are not billed. In batch() it applies to every file.
   */
  pageRange?: string;
  /**
   * Required with model 'fields': the column names you want, as an array or a
   * comma-separated string (max 60).
   */
  fields?: string | string[];
  /** With model 'fields': 'page' (default) one row per page, 'list' one row per printed item. */
  fieldsMode?: FieldsMode;
}

export interface ConvertOptions extends ExtractionOptions {
  model?: ApiModel;
  output?: OutputFormat;
  filename?: string;
}

export interface CreateJobOptions extends ExtractionOptions {
  model?: ApiModel;
  webhookUrl?: string;
  filename?: string;
}

export interface BatchOptions extends ExtractionOptions {
  model?: ApiModel;
  webhookUrl?: string;
  filenames?: string[];
}

/** Adds only the options that are set: an empty value would reach the server as '' instead of 'absent'. */
function appendExtractionOptions(form: FormData, options: ExtractionOptions): void {
  const pageRange = (options.pageRange || '').trim();
  if (pageRange) form.append('page_range', pageRange);
  const fields = Array.isArray(options.fields)
    ? options.fields.map((f) => String(f).trim()).filter(Boolean).join(',')
    : (options.fields || '').trim();
  if (fields) form.append('fields', fields);
  if (options.fieldsMode) form.append('fields_mode', options.fieldsMode);
}

function toBlobPart(data: Buffer | Uint8Array): Blob {
  // Copy into a fresh ArrayBuffer-backed Uint8Array so Blob is happy under TS strict.
  // Buffer's underlying ArrayBufferLike may be SharedArrayBuffer which Blob refuses.
  const copy = new Uint8Array(data.byteLength);
  copy.set(data);
  return new Blob([copy]);
}

async function inputToBlobName(
  input: FileInput,
  fallbackName?: string,
): Promise<{ blob: Blob; name: string }> {
  if (typeof input === 'string') {
    // file path
    const buf = await fs.readFile(input);
    return {
      blob: toBlobPart(buf),
      name: fallbackName || basename(input),
    };
  }
  if (input instanceof Blob) {
    return { blob: input, name: fallbackName || 'upload.bin' };
  }
  if (Buffer.isBuffer(input) || input instanceof Uint8Array) {
    return {
      blob: toBlobPart(input),
      name: fallbackName || 'upload.bin',
    };
  }
  if (input && typeof input === 'object' && 'data' in input) {
    const { data, filename } = input;
    if (data instanceof Blob) return { blob: data, name: filename || fallbackName || 'upload.bin' };
    return {
      blob: toBlobPart(data),
      name: filename || fallbackName || 'upload.bin',
    };
  }
  throw new TypeError(`Unsupported file input type: ${typeof input}`);
}

export class MyOCRClient {
  readonly apiKey: string;
  readonly baseUrl: string;
  readonly timeoutMs: number;
  readonly retryAttempts: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: MyOCRClientOptions = {}) {
    const envKey = typeof process !== 'undefined' ? process.env?.MYOCR_API_KEY : undefined;
    this.apiKey = (options.apiKey || envKey || '').trim();
    if (!this.apiKey) {
      throw new MissingApiKey('apiKey required (pass option or set MYOCR_API_KEY env var)');
    }
    const envBase = typeof process !== 'undefined' ? process.env?.MYOCR_BASE_URL : undefined;
    this.baseUrl = (options.baseUrl || envBase || DEFAULT_BASE_URL).replace(/\/$/, '');
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.retryAttempts = Math.max(1, options.retryAttempts ?? DEFAULT_RETRY_ATTEMPTS);
    this.fetchImpl = options.fetchImpl || globalThis.fetch;
    if (!this.fetchImpl) {
      throw new Error('No fetch implementation available. Use Node 18+ or pass fetchImpl option.');
    }
  }

  private headers(): Record<string, string> {
    return {
      'X-API-Key': this.apiKey,
      'User-Agent': `myocr-client-node/${SDK_VERSION}`,
    };
  }

  private async request(method: string, path: string, init: RequestInit = {}): Promise<Response> {
    const url = `${this.baseUrl}${path}`;
    const headers = { ...this.headers(), ...(init.headers as Record<string, string> | undefined) };

    let lastErr: Error | undefined;
    for (let attempt = 0; attempt < this.retryAttempts; attempt++) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);
      try {
        const resp = await this.fetchImpl(url, {
          method,
          headers,
          body: init.body,
          signal: controller.signal,
        });
        clearTimeout(timer);
        if (RETRYABLE_STATUS.has(resp.status) && attempt < this.retryAttempts - 1) {
          const retryAfter = resp.headers.get('Retry-After');
          const delay = retryAfter ? Number(retryAfter) * 1000 : Math.pow(2, attempt) * 1000;
          await new Promise<void>((r) => setTimeout(r, delay));
          continue;
        }
        return resp;
      } catch (e) {
        clearTimeout(timer);
        lastErr = e as Error;
        if (attempt < this.retryAttempts - 1) {
          const delay = Math.pow(2, attempt) * 1000;
          await new Promise<void>((r) => setTimeout(r, delay));
          continue;
        }
      }
    }
    throw new InternalError(`network error: ${lastErr?.message}`, { statusCode: 0 });
  }

  private async raiseIfError(resp: Response): Promise<void> {
    if (resp.ok) return;
    const requestId = resp.headers.get('X-MyOCR-Request-Id') || undefined;
    let body: unknown;
    const contentType = resp.headers.get('Content-Type') || '';
    if (contentType.includes('application/json')) {
      try {
        body = await resp.json();
      } catch {
        body = await resp.text();
      }
    } else {
      body = await resp.text();
    }
    throw fromResponse(resp.status, body, requestId);
  }

  // ---------- Status ----------

  async status(): Promise<Record<string, unknown>> {
    const resp = await this.request('GET', '/v1/status');
    await this.raiseIfError(resp);
    const json = (await resp.json()) as { data?: Record<string, unknown> };
    return json.data || {};
  }

  async usage(): Promise<Record<string, unknown>> {
    const resp = await this.request('GET', '/v1/usage');
    await this.raiseIfError(resp);
    const json = (await resp.json()) as { data?: Record<string, unknown> };
    return json.data || {};
  }

  // ---------- Sync convert ----------

  async convert(file: FileInput, options: ConvertOptions = {}): Promise<ConversionResult> {
    const model = options.model || 'tables';
    const output = options.output || 'xlsx';
    const { blob, name } = await inputToBlobName(file, options.filename);

    const form = new FormData();
    form.append('file', blob, name);
    form.append('model', model);
    form.append('output', output);
    appendExtractionOptions(form, options);

    const resp = await this.request('POST', '/v1/convert', { body: form });
    await this.raiseIfError(resp);

    const requestId = resp.headers.get('X-MyOCR-Request-Id') || undefined;
    const pagesUsedH = resp.headers.get('X-MyOCR-Pages-Used');
    const pagesUsed = pagesUsedH ? Number(pagesUsedH) : undefined;
    const modelUsed = resp.headers.get('X-MyOCR-Model') || model;
    const ctype = (resp.headers.get('Content-Type') || '').toLowerCase();

    if (ctype.includes('application/json')) {
      const body = (await resp.json()) as { data?: Record<string, unknown> };
      return new ConversionResult({
        format: 'json',
        data: body.data,
        requestId,
        pagesUsed,
        model: modelUsed,
      });
    }
    const ab = await resp.arrayBuffer();
    return new ConversionResult({
      format: ctype.includes('text/plain') ? 'txt' : 'xlsx',
      content: new Uint8Array(ab),
      requestId,
      pagesUsed,
      model: modelUsed,
    });
  }

  // ---------- Async jobs ----------

  async createJob(file: FileInput, options: CreateJobOptions = {}): Promise<Job> {
    const model = options.model || 'tables';
    const { blob, name } = await inputToBlobName(file, options.filename);

    const form = new FormData();
    form.append('file', blob, name);
    form.append('model', model);
    appendExtractionOptions(form, options);
    if (options.webhookUrl) form.append('webhook_url', options.webhookUrl);

    const resp = await this.request('POST', '/v1/jobs', { body: form });
    await this.raiseIfError(resp);
    const body = (await resp.json()) as { data?: JobData };
    return new Job(body.data || ({ request_id: '', status: 'pending' } as JobData), this);
  }

  async getJob(requestId: string): Promise<Job> {
    const resp = await this.request('GET', `/v1/jobs/${encodeURIComponent(requestId)}`);
    await this.raiseIfError(resp);
    const body = (await resp.json()) as { data?: JobData };
    return new Job(body.data || ({ request_id: requestId, status: 'pending' } as JobData), this);
  }

  async getJobResult(requestId: string): Promise<JobResult> {
    const resp = await this.request('GET', `/v1/jobs/${encodeURIComponent(requestId)}/result`);
    await this.raiseIfError(resp);
    const ctype = (resp.headers.get('Content-Type') || '').toLowerCase();
    if (ctype.includes('application/json')) {
      const body = (await resp.json()) as { data?: { result_url?: string; expires_in?: number } };
      return new JobResult({
        resultUrl: body.data?.result_url,
        expiresIn: body.data?.expires_in,
      });
    }
    const ab = await resp.arrayBuffer();
    return new JobResult({
      content: new Uint8Array(ab),
      contentType: ctype,
    });
  }

  async deleteJob(requestId: string): Promise<Record<string, unknown>> {
    const resp = await this.request('DELETE', `/v1/jobs/${encodeURIComponent(requestId)}`);
    await this.raiseIfError(resp);
    const body = (await resp.json()) as { data?: Record<string, unknown> };
    return body.data || {};
  }

  // ---------- Batch ----------

  async batch(files: FileInput[], options: BatchOptions = {}): Promise<BatchResult> {
    if (!files.length) throw new Error('files array cannot be empty');
    if (files.length > 20) throw new Error('max 20 files per batch');
    const model = options.model || 'tables';
    const filenames = options.filenames || [];
    if (filenames.length && filenames.length !== files.length) {
      throw new Error('filenames length must match files length');
    }

    const form = new FormData();
    for (let i = 0; i < files.length; i++) {
      const { blob, name } = await inputToBlobName(files[i], filenames[i]);
      form.append('files', blob, name);
    }
    form.append('model', model);
    appendExtractionOptions(form, options);
    if (options.webhookUrl) form.append('webhook_url', options.webhookUrl);

    const resp = await this.request('POST', '/v1/batch', { body: form });
    await this.raiseIfError(resp);
    const body = (await resp.json()) as {
      data?: {
        batch_id?: string;
        model?: string;
        jobs?: Array<{ filename: string; request_id: string; status: string }>;
        errors?: Array<{ filename: string; code: string; message: string }>;
      };
    };
    const d = body.data || {};
    return new BatchResult({
      batchId: d.batch_id || '',
      model: d.model || model,
      jobs: (d.jobs || []).map(
        (j) => new Job({ request_id: j.request_id, status: j.status, model: d.model || model, filename: j.filename } as JobData, this),
      ),
      errors: d.errors || [],
    });
  }

  // ---------- Keys (session-auth in browser; kept for parity) ----------

  async listKeys(): Promise<Array<Record<string, unknown>>> {
    const resp = await this.request('GET', '/v1/keys');
    await this.raiseIfError(resp);
    const body = (await resp.json()) as { data?: Array<Record<string, unknown>> };
    return body.data || [];
  }

  /**
   * Rotate an API key atomically (revoke + new). Returns the new raw key once.
   * Requires session login (not X-API-Key).
   */
  async rotateKey(keyId: number): Promise<Record<string, unknown>> {
    const resp = await this.request('POST', `/v1/keys/${keyId}/rotate`);
    await this.raiseIfError(resp);
    const body = (await resp.json()) as { data?: Record<string, unknown> };
    return body.data || {};
  }

  /** GET /v1/jobs — list paginated jobs for the calling API key. */
  async listJobs(options: { status?: string; model?: ApiModel; limit?: number; offset?: number } = {}): Promise<{
    total: number;
    limit: number;
    offset: number;
    jobs: JobData[];
  }> {
    const params = new URLSearchParams();
    params.set('limit', String(Math.min(options.limit ?? 20, 100)));
    params.set('offset', String(Math.max(options.offset ?? 0, 0)));
    if (options.status) params.set('status', options.status);
    if (options.model) params.set('model', options.model);
    const resp = await this.request('GET', `/v1/jobs?${params.toString()}`);
    await this.raiseIfError(resp);
    const body = (await resp.json()) as { data?: { total: number; limit: number; offset: number; jobs: JobData[] } };
    return body.data || { total: 0, limit: 0, offset: 0, jobs: [] };
  }
}

export { JobStatus };
