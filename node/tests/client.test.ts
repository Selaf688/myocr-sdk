import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createHmac } from 'node:crypto';
import {
  MyOCRClient,
  MissingApiKey,
  InvalidApiKey,
  QuotaExceeded,
  FileTooLarge,
  UnsupportedModel,
  NotFound,
  NotReady,
  RateLimited,
  OcrEngineError,
  JobStatus,
  verifyWebhookSignature,
} from '../src/index.js';

const BASE = 'https://api.myocr.app';

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

function binResponse(content: Uint8Array, status = 200, contentType: string, headers: Record<string, string> = {}): Response {
  return new Response(content, {
    status,
    headers: { 'Content-Type': contentType, ...headers },
  });
}

function makeFetch(mockResponse: Response | ((url: string, init?: RequestInit) => Response)): typeof fetch {
  return vi.fn(async (input: string | URL | Request) => {
    if (typeof mockResponse === 'function') {
      return mockResponse(String(input));
    }
    return mockResponse;
  }) as unknown as typeof fetch;
}

describe('MyOCRClient', () => {
  let client: MyOCRClient;

  beforeEach(() => {
    process.env.MYOCR_API_KEY = 'sk_test_dummy';
  });

  afterEach(() => {
    delete process.env.MYOCR_API_KEY;
  });

  it('throws MissingApiKey if no key', () => {
    delete process.env.MYOCR_API_KEY;
    expect(() => new MyOCRClient({ baseUrl: BASE })).toThrow(MissingApiKey);
  });

  it('reads api key from env', () => {
    process.env.MYOCR_API_KEY = 'sk_live_envtest';
    const c = new MyOCRClient({ baseUrl: BASE });
    expect(c.apiKey).toBe('sk_live_envtest');
  });

  it('status() returns data', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(jsonResponse({ success: true, data: { service: 'myocr.app API', version: 'v1' } })),
    });
    const out = await client.status();
    expect(out.service).toBe('myocr.app API');
  });

  it('usage() returns quota data', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(
        jsonResponse({
          success: true,
          data: { plan: 'free', calls_used: 42, calls_limit: 100, percentage: 42.0, reset_date: '2026-06-01T00:00:00', year_month: '2026-05', is_test_key: false },
        }),
      ),
    });
    const u = await client.usage();
    expect(u.calls_used).toBe(42);
    expect(u.plan).toBe('free');
  });

  it('convert() returns xlsx ConversionResult', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(
        binResponse(new TextEncoder().encode('FAKEXLSX'), 200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', {
          'X-MyOCR-Request-Id': 'abc123',
          'X-MyOCR-Pages-Used': '3',
          'X-MyOCR-Model': 'invoice',
        }),
      ),
    });
    const result = await client.convert({ data: Buffer.from('%PDF-1.4'), filename: 'in.pdf' }, { model: 'invoice' });
    expect(result.format).toBe('xlsx');
    expect(result.pagesUsed).toBe(3);
    expect(result.model).toBe('invoice');
    expect(result.requestId).toBe('abc123');
    expect(new TextDecoder().decode(result.content!)).toBe('FAKEXLSX');
  });

  it('convert() returns txt for model=text', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(binResponse(new TextEncoder().encode('hello world'), 200, 'text/plain; charset=utf-8')),
    });
    const result = await client.convert({ data: Buffer.from('x'), filename: 'in.pdf' }, { model: 'text' });
    expect(result.format).toBe('txt');
    expect(result.text()).toBe('hello world');
  });

  it('convert() returns json envelope when output=json', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(jsonResponse({ success: true, data: { pages: 2, tables: 1 } })),
    });
    const r = await client.convert({ data: Buffer.from('x'), filename: 'in.pdf' }, { output: 'json' });
    expect(r.format).toBe('json');
    expect(r.json().pages).toBe(2);
  });

  it('convert() throws InvalidApiKey on 401', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(
        jsonResponse(
          { success: false, error: { code: 'INVALID_API_KEY', message: 'API key not found' }, request_id: 'r3' },
          401,
        ),
      ),
    });
    await expect(client.convert({ data: Buffer.from('x'), filename: 'in.pdf' })).rejects.toBeInstanceOf(InvalidApiKey);
  });

  it('convert() throws QuotaExceeded with extra fields', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(
        jsonResponse(
          {
            success: false,
            error: {
              code: 'QUOTA_EXCEEDED',
              message: 'Quota exceeded',
              upgrade_url: 'https://myocr.app/account/api',
              calls_used: 50,
              calls_limit: 50,
              reset_date: '2026-06-01T00:00:00',
              current_plan: 'free',
            },
          },
          402,
        ),
      ),
    });
    try {
      await client.convert({ data: Buffer.from('x'), filename: 'in.pdf' });
      throw new Error('expected throw');
    } catch (e) {
      expect(e).toBeInstanceOf(QuotaExceeded);
      const q = e as QuotaExceeded;
      expect(q.upgradeUrl).toBe('https://myocr.app/account/api');
      expect(q.callsUsed).toBe(50);
      expect(q.currentPlan).toBe('free');
    }
  });

  it('convert() throws FileTooLarge on 413', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(jsonResponse({ success: false, error: { code: 'FILE_TOO_LARGE', message: 'Max 5MB' } }, 413)),
    });
    await expect(client.convert({ data: Buffer.from('x'), filename: 'in.pdf' })).rejects.toBeInstanceOf(FileTooLarge);
  });

  it('convert() throws UnsupportedModel', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(jsonResponse({ success: false, error: { code: 'UNSUPPORTED_MODEL', message: '...' } }, 400)),
    });
    await expect(
      // @ts-expect-error testing invalid model
      client.convert({ data: Buffer.from('x'), filename: 'in.pdf' }, { model: 'bogus' }),
    ).rejects.toBeInstanceOf(UnsupportedModel);
  });

  it('convert() throws OcrEngineError on 502', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(jsonResponse({ success: false, error: { code: 'OCR_ERROR', message: 'fail' } }, 502)),
    });
    await expect(client.convert({ data: Buffer.from('x'), filename: 'in.pdf' }, { model: 'invoice' })).rejects.toBeInstanceOf(OcrEngineError);
  });

  it('convert() throws RateLimited on 429', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(jsonResponse({ success: false, error: { code: 'RATE_LIMITED', message: 'slow' } }, 429)),
    });
    await expect(client.convert({ data: Buffer.from('x'), filename: 'in.pdf' })).rejects.toBeInstanceOf(RateLimited);
  });

  it('createJob() returns Job pending', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(
        jsonResponse({ success: true, data: { request_id: 'j1', status: 'pending', model: 'invoice' } }),
      ),
    });
    const job = await client.createJob({ data: Buffer.from('x'), filename: 'in.pdf' }, { model: 'invoice', webhookUrl: 'https://my.app/wh' });
    expect(job.requestId).toBe('j1');
    expect(job.status).toBe(JobStatus.Pending);
    expect(job.model).toBe('invoice');
  });

  it('getJob() returns Job done', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(
        jsonResponse({
          success: true,
          data: {
            request_id: 'j1',
            status: 'done',
            model: 'invoice',
            pages_used: 5,
            created_at: '2026-05-25T10:00:00',
            completed_at: '2026-05-25T10:00:30',
          },
        }),
      ),
    });
    const job = await client.getJob('j1');
    expect(job.isDone).toBe(true);
    expect(job.pagesUsed).toBe(5);
  });

  it('Job.wait() polls until terminal', async () => {
    let callCount = 0;
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(() => {
        callCount++;
        const status = callCount === 1 ? 'processing' : 'done';
        return jsonResponse({ success: true, data: { request_id: 'jX', status, model: 'invoice', pages_used: 2 } });
      }),
    });
    const job = await client.getJob('jX');
    // first response was 'processing' so .isTerminal=false
    expect(callCount).toBe(1);
    if (!job.isTerminal) {
      await job.wait({ timeoutMs: 5000, initialDelayMs: 10, maxDelayMs: 50 });
    }
    expect(job.isDone).toBe(true);
  });

  it('getJobResult() returns signed URL', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(
        jsonResponse({ success: true, data: { result_url: 'https://r2.example/out.xlsx', expires_in: 86400 } }),
      ),
    });
    const r = await client.getJobResult('jY');
    expect(r.resultUrl).toBe('https://r2.example/out.xlsx');
    expect(r.expiresIn).toBe(86400);
  });

  it('getJobResult() throws NotReady on 409', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(jsonResponse({ success: false, error: { code: 'NOT_READY', message: 'processing' } }, 409)),
    });
    await expect(client.getJobResult('jZ')).rejects.toBeInstanceOf(NotReady);
  });

  it('deleteJob() returns deleted=true', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(jsonResponse({ success: true, data: { request_id: 'jW', deleted: true } })),
    });
    const out = await client.deleteJob('jW');
    expect(out.deleted).toBe(true);
  });

  it('getJob() throws NotFound', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(jsonResponse({ success: false, error: { code: 'NOT_FOUND', message: 'Job not found' } }, 404)),
    });
    await expect(client.getJob('missing')).rejects.toBeInstanceOf(NotFound);
  });

  it('batch() returns BatchResult', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(
        jsonResponse({
          success: true,
          data: {
            batch_id: 'B1',
            model: 'invoice',
            jobs_created: 2,
            jobs: [
              { filename: 'a.pdf', request_id: 'j1', status: 'pending' },
              { filename: 'b.pdf', request_id: 'j2', status: 'pending' },
            ],
            errors: [{ filename: 'c.pdf', code: 'UNSUPPORTED_FILE_TYPE', message: 'ext' }],
          },
        }),
      ),
    });
    const result = await client.batch(
      [
        { data: Buffer.from('a'), filename: 'a.pdf' },
        { data: Buffer.from('b'), filename: 'b.pdf' },
      ],
      { model: 'invoice' },
    );
    expect(result.batchId).toBe('B1');
    expect(result.jobsCreated).toBe(2);
    expect(result.errors).toHaveLength(1);
    expect(result.jobs[0].requestId).toBe('j1');
  });

  it('convert() sends pageRange, fields (array) and fieldsMode', async () => {
    const fetchImpl = makeFetch(binResponse(new Uint8Array([1]), 200,
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'));
    client = new MyOCRClient({ baseUrl: BASE, retryAttempts: 1, fetchImpl });
    await client.convert(new Uint8Array([1, 2]), {
      filename: 'a.pdf', model: 'fields', pageRange: ' 2-4 ',
      fields: ['Date', ' Amount ', ''], fieldsMode: 'list',
    });
    const form = (fetchImpl as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0][1].body as FormData;
    expect(form.get('model')).toBe('fields');
    expect(form.get('page_range')).toBe('2-4');
    expect(form.get('fields')).toBe('Date,Amount');
    expect(form.get('fields_mode')).toBe('list');
  });

  it('convert() omits unset extraction options', async () => {
    const fetchImpl = makeFetch(binResponse(new Uint8Array([1]), 200,
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'));
    client = new MyOCRClient({ baseUrl: BASE, retryAttempts: 1, fetchImpl });
    await client.convert(new Uint8Array([1]), { filename: 'a.pdf', pageRange: '  ', fields: [] });
    const form = (fetchImpl as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0][1].body as FormData;
    expect(form.has('page_range')).toBe(false);
    expect(form.has('fields')).toBe(false);
    expect(form.has('fields_mode')).toBe(false);
  });

  it('createJob() and batch() send pageRange and fields (string)', async () => {
    const jobFetch = makeFetch(jsonResponse({ success: true, data: { request_id: 'r1', status: 'pending' } }, 202));
    client = new MyOCRClient({ baseUrl: BASE, retryAttempts: 1, fetchImpl: jobFetch });
    await client.createJob(new Uint8Array([1]), { filename: 'a.pdf', pageRange: '1,3-5', fields: 'Date,Total', model: 'fields' });
    let form = (jobFetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0][1].body as FormData;
    expect(form.get('page_range')).toBe('1,3-5');
    expect(form.get('fields')).toBe('Date,Total');

    const batchFetch = makeFetch(jsonResponse({ success: true, data: { batch_id: 'b1', model: 'tables', jobs: [], errors: [] } }, 202));
    client = new MyOCRClient({ baseUrl: BASE, retryAttempts: 1, fetchImpl: batchFetch });
    await client.batch([new Uint8Array([1]), new Uint8Array([2])], { filenames: ['a.pdf', 'b.pdf'], pageRange: '2-' });
    form = (batchFetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0][1].body as FormData;
    expect(form.get('page_range')).toBe('2-');
    expect(form.getAll('files').length).toBe(2);
  });

  it('batch() jobs keep their filename even when a file is rejected', async () => {
    client = new MyOCRClient({
      baseUrl: BASE, retryAttempts: 1,
      fetchImpl: makeFetch(jsonResponse({ success: true, data: {
        batch_id: 'B1', model: 'tables',
        jobs: [{ filename: 'b.pdf', request_id: 'j2', status: 'pending' }],
        errors: [{ filename: 'a.pdf', code: 'UNSUPPORTED_FILE_TYPE', message: 'x' }],
      } }, 202)),
    });
    const r = await client.batch([new Uint8Array([1]), new Uint8Array([2])], { filenames: ['a.pdf', 'b.pdf'] });
    expect(r.jobs.map((j) => j.filename)).toEqual(['b.pdf']);
    expect(r.errors[0].filename).toBe('a.pdf');
  });

  it('sends a User-Agent with the package version', async () => {
    const { readFileSync } = await import('node:fs');
    const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
    const fetchImpl = makeFetch(jsonResponse({ success: true, data: {} }));
    client = new MyOCRClient({ baseUrl: BASE, retryAttempts: 1, fetchImpl });
    await client.status();
    const headers = (fetchImpl as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0][1].headers as Record<string, string>;
    expect(headers['User-Agent']).toBe(`myocr-client-node/${pkg.version}`);
  });

  it('batch() rejects empty files', async () => {
    client = new MyOCRClient({ baseUrl: BASE, retryAttempts: 1, fetchImpl: makeFetch(jsonResponse({}, 200)) });
    await expect(client.batch([])).rejects.toThrow('empty');
  });

  it('batch() rejects > 20 files', async () => {
    client = new MyOCRClient({ baseUrl: BASE, retryAttempts: 1, fetchImpl: makeFetch(jsonResponse({}, 200)) });
    const many = new Array(21).fill({ data: Buffer.from('x'), filename: 'f.pdf' });
    await expect(client.batch(many)).rejects.toThrow('max 20');
  });

  it('rotateKey() returns new key payload', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(
        jsonResponse({
          success: true,
          data: {
            old_id: 42, old_revoked: true,
            id: 43, key: 'sk_live_NEW', prefix: 'sk_live_NE',
            label: 'main', is_test: false,
            created_at: '2026-05-26T10:00:00', note: 'store now',
          },
        }),
      ),
    });
    const out = await client.rotateKey(42);
    expect(out.old_id).toBe(42);
    expect(out.old_revoked).toBe(true);
    expect(out.key).toBe('sk_live_NEW');
  });

  it('listJobs() returns paginated list', async () => {
    client = new MyOCRClient({
      baseUrl: BASE,
      retryAttempts: 1,
      fetchImpl: makeFetch(
        jsonResponse({
          success: true,
          data: {
            total: 2, limit: 10, offset: 0,
            jobs: [
              { request_id: 'j1', status: 'done', model: 'invoice', pages_used: 3 },
              { request_id: 'j2', status: 'done', model: 'invoice', pages_used: 5 },
            ],
          },
        }),
      ),
    });
    const out = await client.listJobs({ status: 'done', model: 'invoice', limit: 10 });
    expect(out.total).toBe(2);
    expect(out.jobs).toHaveLength(2);
    expect(out.jobs[0].request_id).toBe('j1');
  });
});

describe('verifyWebhookSignature', () => {
  it('returns true for valid signature', () => {
    const body = Buffer.from('{"event":"job.completed","data":{"request_id":"j1"}}');
    const secret = 'supersecret';
    const sig = 'sha256=' + createHmac('sha256', secret).update(body).digest('hex');
    expect(verifyWebhookSignature(body, sig, secret)).toBe(true);
  });

  it('returns false for invalid signature', () => {
    const body = Buffer.from('{"event":"job.completed"}');
    expect(verifyWebhookSignature(body, 'sha256=000000', 'k')).toBe(false);
    expect(verifyWebhookSignature(body, '', 'k')).toBe(false);
    expect(verifyWebhookSignature(body, 'sha256=abc', '')).toBe(false);
  });

  it('accepts string body', () => {
    const body = '{"event":"job.failed"}';
    const secret = 'k';
    const sig = 'sha256=' + createHmac('sha256', secret).update(body).digest('hex');
    expect(verifyWebhookSignature(body, sig, secret)).toBe(true);
  });

  it('tolerates hex without sha256= prefix', () => {
    const body = Buffer.from('x');
    const secret = 'k';
    const hex = createHmac('sha256', secret).update(body).digest('hex');
    expect(verifyWebhookSignature(body, hex, secret)).toBe(true);
  });
});
