"""Receive job notifications from myocr.

Create jobs with webhook_url="https://your.app/webhooks/myocr" and myocr POSTs
{"event": "job.completed" | "job.failed", "data": {"request_id": ...}} when each
job ends. Treat it as a signal: confirm the job with your own key before acting,
so a forged request cannot make you trust or download anything.

    pip install myocr-client flask
    export MYOCR_API_KEY=sk_live_...
    flask --app webhook_receiver run --port 8000
"""
from flask import Flask, request

from myocr_client import MyOCRClient, NotFound

app = Flask(__name__)
client = MyOCRClient()  # reads MYOCR_API_KEY


@app.post("/webhooks/myocr")
def myocr_webhook():
    event = request.get_json(silent=True) or {}
    request_id = (event.get("data") or {}).get("request_id")
    if not request_id:
        return "", 204
    try:
        job = client.get_job(request_id)  # authenticated: the API is the source of truth
    except NotFound:
        return "", 204  # not one of your jobs
    if job.is_done:
        job.download(f"{request_id}.xlsx")
        app.logger.info("Saved %s.xlsx", request_id)
    elif job.is_failed:
        app.logger.warning("Job %s failed: %s", request_id, job.error_detail)
    return "", 204
