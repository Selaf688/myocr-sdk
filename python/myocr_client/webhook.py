"""Helper for verifying the HMAC signature of incoming webhooks.

myocr signs every webhook with an `X-MyOCR-Signature: sha256=<hex>` header, computed
as the HMAC-SHA256 of the raw body using the `WEBHOOK_SIGNING_SECRET` you configured
on the server side as the key.

Example (Flask):

    from flask import request
    from myocr_client import verify_webhook_signature, MyOCRError

    @app.route("/webhooks/myocr", methods=["POST"])
    def myocr_webhook():
        body = request.get_data()  # raw bytes, not parsed JSON!
        sig = request.headers.get("X-MyOCR-Signature", "")
        if not verify_webhook_signature(body, sig, secret="my-shared-secret"):
            return "invalid signature", 401
        event = request.get_json()
        # event = {"event": "job.completed", "data": {"request_id": "...", ...}}
        return "", 200

Important: use `request.get_data()` (raw), NOT `request.get_json()` — the signature
is computed over the body byte-for-byte as received, not over re-serialized JSON.
"""
import hashlib
import hmac
from typing import Union


def verify_webhook_signature(
    body: Union[bytes, str],
    signature: str,
    secret: str,
) -> bool:
    """Verify the HMAC-SHA256 of the body against a shared secret.

    Args:
        body: the raw bytes received (NOT the parsed JSON).
        signature: value of the 'X-MyOCR-Signature' header (format 'sha256=<hex>').
        secret: the WEBHOOK_SIGNING_SECRET shared with the myocr server.

    Returns:
        True if the signature is valid, False otherwise.

    Uses hmac.compare_digest to prevent timing attacks.
    """
    if not signature or not secret:
        return False
    if isinstance(body, str):
        body = body.encode("utf-8")
    if not isinstance(secret, str):
        secret = str(secret)

    # Expected format: "sha256=<hex>"
    expected_prefix = "sha256="
    if signature.startswith(expected_prefix):
        received = signature[len(expected_prefix):].strip()
    else:
        # Also accept a bare hex digest, for leniency
        received = signature.strip()

    computed = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(received, computed)
