/**
 * Helper to verify the HMAC signature of incoming webhooks.
 *
 * myocr signs every webhook with HMAC-SHA256 (header `X-MyOCR-Signature: sha256=<hex>`)
 * computed over the raw body bytes, using your configured `WEBHOOK_SIGNING_SECRET`.
 *
 * Example (Express):
 *
 *     import express from 'express';
 *     import { verifyWebhookSignature } from 'myocr-client';
 *
 *     const app = express();
 *     // IMPORTANT: capture raw body. Express's default json parser destroys it.
 *     app.use('/webhooks/myocr', express.raw({ type: 'application/json' }));
 *
 *     app.post('/webhooks/myocr', (req, res) => {
 *       const body: Buffer = req.body; // raw bytes
 *       const sig = req.header('X-MyOCR-Signature') || '';
 *       if (!verifyWebhookSignature(body, sig, 'shared-secret')) {
 *         return res.status(401).send('invalid signature');
 *       }
 *       const event = JSON.parse(body.toString('utf8'));
 *       // event = { event: 'job.completed', data: { request_id: ..., ... } }
 *       res.status(200).end();
 *     });
 *
 * Important: pass the raw bytes (Buffer / Uint8Array / string of the original body),
 * NOT the parsed JSON re-serialized — whitespace and key order would break the signature.
 */
import { createHmac, timingSafeEqual } from 'node:crypto';

export function verifyWebhookSignature(
  body: Buffer | Uint8Array | string,
  signature: string,
  secret: string,
): boolean {
  if (!signature || !secret) return false;

  const bodyBuf: Buffer =
    typeof body === 'string'
      ? Buffer.from(body, 'utf8')
      : Buffer.isBuffer(body)
        ? body
        : Buffer.from(body);

  // Format: "sha256=<hex>", tolerate plain hex too.
  const prefix = 'sha256=';
  const received = signature.startsWith(prefix) ? signature.slice(prefix.length).trim() : signature.trim();

  const expected = createHmac('sha256', secret).update(bodyBuf).digest('hex');

  // Buffers must be same length for timingSafeEqual
  if (received.length !== expected.length) return false;

  try {
    return timingSafeEqual(Buffer.from(received, 'hex'), Buffer.from(expected, 'hex'));
  } catch {
    return false;
  }
}
