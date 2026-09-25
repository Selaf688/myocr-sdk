/**
 * Typed exceptions mapped 1:1 to API error codes (see static/openapi.yaml).
 *
 * All custom exceptions extend MyOCRError. The client raises the right one
 * based on the `error.code` field of the JSON envelope, or HTTP status when
 * the body is not JSON.
 */

export class MyOCRError extends Error {
  code?: string;
  requestId?: string;
  statusCode?: number;
  payload?: Record<string, unknown>;

  constructor(
    message: string,
    opts: {
      code?: string;
      requestId?: string;
      statusCode?: number;
      payload?: Record<string, unknown>;
    } = {},
  ) {
    super(message || opts.code || 'myocr error');
    this.name = this.constructor.name;
    this.code = opts.code;
    this.requestId = opts.requestId;
    this.statusCode = opts.statusCode;
    this.payload = opts.payload;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class MissingApiKey extends MyOCRError {}
export class InvalidApiKey extends MyOCRError {}
export class UnsupportedModel extends MyOCRError {}
export class UnsupportedFileType extends MyOCRError {}
export class MissingFile extends MyOCRError {}
export class FileTooLarge extends MyOCRError {}
export class TooManyPages extends MyOCRError {}
export class InvalidWebhookUrl extends MyOCRError {}
export class NotReady extends MyOCRError {}
export class NotFound extends MyOCRError {}
export class OcrEngineError extends MyOCRError {}
export class StorageError extends MyOCRError {}
export class ServiceNotReady extends MyOCRError {}
export class RateLimited extends MyOCRError {}
export class InternalError extends MyOCRError {}

export class QuotaExceeded extends MyOCRError {
  upgradeUrl?: string;
  callsUsed?: number;
  callsLimit?: number;
  resetDate?: string;
  currentPlan?: string;

  constructor(message: string, opts: ConstructorParameters<typeof MyOCRError>[1] = {}) {
    super(message, opts);
    const err = (opts.payload as { error?: Record<string, unknown> } | undefined)?.error;
    if (err && typeof err === 'object') {
      this.upgradeUrl = err.upgrade_url as string | undefined;
      this.callsUsed = err.calls_used as number | undefined;
      this.callsLimit = err.calls_limit as number | undefined;
      this.resetDate = err.reset_date as string | undefined;
      this.currentPlan = err.current_plan as string | undefined;
    }
  }
}

const CODE_TO_EXCEPTION: Record<string, typeof MyOCRError> = {
  MISSING_API_KEY: MissingApiKey,
  INVALID_API_KEY: InvalidApiKey,
  UNSUPPORTED_MODEL: UnsupportedModel,
  UNSUPPORTED_FILE_TYPE: UnsupportedFileType,
  MISSING_FILE: MissingFile,
  FILE_TOO_LARGE: FileTooLarge,
  TOO_MANY_PAGES: TooManyPages,
  INVALID_WEBHOOK_URL: InvalidWebhookUrl,
  QUOTA_EXCEEDED: QuotaExceeded,
  INSUFFICIENT_CREDITS: QuotaExceeded,
  quota_exceeded: QuotaExceeded,
  NOT_READY: NotReady,
  NOT_FOUND: NotFound,
  OCR_ERROR: OcrEngineError,
  STORAGE_ERROR: StorageError,
  SERVICE_NOT_READY: ServiceNotReady,
  INTERNAL_ERROR: InternalError,
};

export function fromResponse(
  statusCode: number,
  body: unknown,
  requestId?: string,
): MyOCRError {
  let code: string | undefined;
  let message = '';
  let payload: Record<string, unknown> | undefined;

  if (body && typeof body === 'object') {
    payload = body as Record<string, unknown>;
    const err = payload.error;
    if (err && typeof err === 'object') {
      const e = err as Record<string, unknown>;
      code = (e.code as string) || undefined;
      message = (e.message as string) || '';
    } else if (typeof err === 'string') {
      code = err;
      message = (payload.message as string) || '';
    }
  } else if (typeof body === 'string') {
    message = body;
  }

  if (statusCode === 429) {
    return new RateLimited(message || 'Rate limit exceeded', { code: code || 'RATE_LIMITED', statusCode, requestId, payload });
  }

  if (code && CODE_TO_EXCEPTION[code]) {
    const Ctor = CODE_TO_EXCEPTION[code];
    return new Ctor(message || code, { code, statusCode, requestId, payload });
  }

  if (statusCode === 401) {
    return new InvalidApiKey(message || 'Unauthorized', { code, statusCode, requestId, payload });
  }
  if (statusCode === 404) {
    return new NotFound(message || 'Not found', { code, statusCode, requestId, payload });
  }
  if (statusCode === 402) {
    return new QuotaExceeded(message || 'Quota exceeded', { code, statusCode, requestId, payload });
  }
  if (statusCode >= 500) {
    return new InternalError(message || `Server error (${statusCode})`, { code, statusCode, requestId, payload });
  }

  return new MyOCRError(message || `HTTP ${statusCode}`, { code, statusCode, requestId, payload });
}
