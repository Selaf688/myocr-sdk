/**
 * Data models returned by the SDK.
 */
import { promises as fs } from 'node:fs';
import type { MyOCRClient } from './client.js';

export type ApiModel =
  | 'tables'
  | 'text'
  | 'invoice'
  | 'receipt'
  | 'bank_statement'
  | 'business_card'
  | 'fields';

/** With model 'fields': 'page' (default) = one row per page, 'list' = one row per printed item. */
export type FieldsMode = 'page' | 'list';

export type OutputFormat = 'xlsx' | 'txt' | 'json';

export enum JobStatus {
  Pending = 'pending',
  Processing = 'processing',
  Done = 'done',
  Failed = 'failed',
}

export interface JobData {
  request_id: string;
  status: string;
  model?: string | null;
  pages_used?: number | null;
  created_at?: string | null;
  completed_at?: string | null;
  error_detail?: string | null;
  /** Set on jobs created by batch(): the uploaded file's name. */
  filename?: string | null;
}

/**
 * Result of `client.convert(...)`.
 * Three possible shapes based on model/output:
 * - xlsx binary: `content` is Uint8Array, `format='xlsx'`
 * - txt: `content` is Uint8Array (decode with .text()), `format='txt'`
 * - json metadata: `data` is object, `format='json'`
 */
export class ConversionResult {
  content?: Uint8Array;
  data?: Record<string, unknown>;
  format: OutputFormat;
  requestId?: string;
  pagesUsed?: number;
  model?: string;

  constructor(init: Partial<ConversionResult> & { format: OutputFormat }) {
    Object.assign(this, init);
    this.format = init.format;
  }

  /** Write content to disk. Throws if format=json (use .json() instead). */
  async save(path: string): Promise<void> {
    if (!this.content) {
      throw new Error(
        `ConversionResult has no binary content (format=${this.format}). Use .json() or .text() instead.`,
      );
    }
    await fs.writeFile(path, this.content);
  }

  /** Decode content as UTF-8. Useful for format='txt'. */
  text(): string {
    if (!this.content) return '';
    return new TextDecoder().decode(this.content);
  }

  /** Return data dict (format=json) or throw. */
  json(): Record<string, unknown> {
    if (!this.data) {
      throw new Error("ConversionResult has no JSON data (format != 'json')");
    }
    return this.data;
  }
}

/**
 * Wrapper for `/v1/jobs/{id}/result`.
 * Two shapes:
 * - signed URL (R2): `resultUrl` set, `expiresIn` in seconds
 * - direct binary: `content` Uint8Array
 */
export class JobResult {
  resultUrl?: string;
  expiresIn?: number;
  content?: Uint8Array;
  contentType?: string;

  constructor(init: Partial<JobResult> = {}) {
    Object.assign(this, init);
  }

  /** Save to disk. If `resultUrl` set, download from signed URL first. */
  async save(path: string): Promise<void> {
    if (this.content) {
      await fs.writeFile(path, this.content);
      return;
    }
    if (this.resultUrl) {
      const resp = await fetch(this.resultUrl);
      if (!resp.ok) throw new Error(`Download failed: ${resp.status}`);
      const buf = new Uint8Array(await resp.arrayBuffer());
      await fs.writeFile(path, buf);
      return;
    }
    throw new Error('JobResult has neither content nor resultUrl');
  }
}

/**
 * Async job. Returned by createJob() and getJob().
 * Use `await job.wait()` to poll until done/failed.
 */
export class Job {
  requestId: string;
  status: JobStatus;
  model?: string | null;
  pagesUsed?: number | null;
  createdAt?: string | null;
  completedAt?: string | null;
  errorDetail?: string | null;
  /** Set on jobs created by batch(): the uploaded file's name. */
  filename?: string | null;

  private _client?: MyOCRClient;

  constructor(init: JobData, client?: MyOCRClient) {
    this.requestId = init.request_id;
    this.status = (init.status as JobStatus) || JobStatus.Pending;
    this.model = init.model;
    this.pagesUsed = init.pages_used ?? undefined;
    this.createdAt = init.created_at;
    this.completedAt = init.completed_at;
    this.errorDetail = init.error_detail;
    this.filename = init.filename;
    this._client = client;
  }

  get isDone(): boolean {
    return this.status === JobStatus.Done;
  }

  get isFailed(): boolean {
    return this.status === JobStatus.Failed;
  }

  get isTerminal(): boolean {
    return this.status === JobStatus.Done || this.status === JobStatus.Failed;
  }

  /** Re-read state from server. Requires the originating client. */
  async refresh(): Promise<Job> {
    if (!this._client) {
      throw new Error('Job not bound to a client (use client.getJob(requestId))');
    }
    const updated = await this._client.getJob(this.requestId);
    this.status = updated.status;
    this.pagesUsed = updated.pagesUsed;
    this.completedAt = updated.completedAt;
    this.errorDetail = updated.errorDetail;
    return this;
  }

  /**
   * Poll with exponential backoff until terminal status.
   * Default timeout 600s, backoff 1s/2s/4s/8s/15s (capped).
   */
  async wait(options: { timeoutMs?: number; initialDelayMs?: number; maxDelayMs?: number } = {}): Promise<Job> {
    const timeoutMs = options.timeoutMs ?? 600_000;
    const initialDelayMs = options.initialDelayMs ?? 1_000;
    const maxDelayMs = options.maxDelayMs ?? 15_000;
    const deadline = Date.now() + timeoutMs;
    let delay = initialDelayMs;
    while (true) {
      await this.refresh();
      if (this.isTerminal) return this;
      if (Date.now() >= deadline) {
        throw new Error(`Job ${this.requestId} still ${this.status} after ${timeoutMs}ms`);
      }
      const sleep = Math.min(delay, Math.max(100, deadline - Date.now()));
      await new Promise<void>((resolve) => setTimeout(resolve, sleep));
      delay = Math.min(delay * 2, maxDelayMs);
    }
  }

  /** Fetch /v1/jobs/{id}/result. Throws NotReady if status != done. */
  async getResult(): Promise<JobResult> {
    if (!this._client) throw new Error('Job not bound to a client');
    return this._client.getJobResult(this.requestId);
  }

  /** Shortcut: getResult().save(path). */
  async download(path: string): Promise<void> {
    const r = await this.getResult();
    await r.save(path);
  }

  /** Delete job + cleanup files. */
  async delete(): Promise<void> {
    if (!this._client) throw new Error('Job not bound to a client');
    await this._client.deleteJob(this.requestId);
  }
}

export interface BatchErrorEntry {
  filename: string;
  code: string;
  message: string;
}

export class BatchResult {
  batchId: string;
  model: string;
  jobs: Job[];
  errors: BatchErrorEntry[];

  constructor(init: {
    batchId: string;
    model: string;
    jobs: Job[];
    errors: BatchErrorEntry[];
  }) {
    this.batchId = init.batchId;
    this.model = init.model;
    this.jobs = init.jobs;
    this.errors = init.errors;
  }

  get jobsCreated(): number {
    return this.jobs.length;
  }

  /** Poll each job sequentially until all are terminal. */
  async waitAll(options: { timeoutMs?: number } = {}): Promise<Job[]> {
    const timeoutMs = options.timeoutMs ?? 1_200_000;
    return Promise.all(this.jobs.map((j) => j.wait({ timeoutMs })));
  }
}
