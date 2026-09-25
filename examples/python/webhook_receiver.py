"""Receive job notifications from myocr and verify their signature.

Create jobs with webhook_url="https://your.app/webhooks/myocr". When each job ends,
myocr POSTs {"event": "job.completed" | "job.failed", "data": {...}} signed with your
account's webhook signing secret: copy it from the API dashboard
(https://www.myocr.app/account/api#webhook-secret).

    pip install myocr-client flask
    export MYOCR_WEBHOOK_SECRET=whsec_...
    flask --app webhook_receiver run --port 8000
"""
import os

import requests
from flask import Flask, request

from myocr_client import verify_webhook_signature

app = Flask(__name__)
SECRET = os.environ["MYOCR_WEBHOOK_SECRET"]


@app.post("/webhooks/myocr")
def myocr_webhook():
    body = request.get_data()  # raw bytes: the signature covers them exactly as sent
    if not verify_webhook_signature(body, request.headers.get("X-MyOCR-Signature", ""), SECRET):
        return "invalid signature", 401

    event = request.get_json()
    data = event.get("data", {})
    if event.get("event") == "job.completed" and data.get("result_url"):
        # Temporary link, valid 24 hours. No API key needed.
        resp = requests.get(data["result_url"], timeout=60)
        resp.raise_for_status()
        with open(f"{data['request_id']}.xlsx", "wb") as f:
            f.write(resp.content)
        app.logger.info("Saved %s.xlsx", data["request_id"])
    elif event.get("event") == "job.failed":
        app.logger.warning("Job %s failed: %s", data.get("request_id"), data.get("error"))
    return "", 204
