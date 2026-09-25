"""Pytest suite for myocr-client.

Uses the `responses` library to mock HTTP. No real network calls, no API key needed.

Run:
    cd python
    pip install -e ".[dev]"
    pytest -v
"""
import json

import pytest
import responses
from responses import matchers

from myocr_client import (
    MyOCRClient,
    MyOCRError,
    InvalidApiKey,
    QuotaExceeded,
    FileTooLarge,
    UnsupportedModel,
    NotFound,
    NotReady,
    RateLimited,
    OcrEngineError,
    Job,
    JobStatus,
    verify_webhook_signature,
)

BASE = "https://api.myocr.app"


@pytest.fixture
def client():
    return MyOCRClient(api_key="sk_test_dummy", base_url=BASE, retry_attempts=1)


# ---------- status ----------

@responses.activate
def test_status_ok(client):
    responses.get(
        f"{BASE}/v1/status",
        json={"success": True, "data": {"service": "myocr.app API", "version": "v1"},
              "request_id": "r1"},
        status=200,
    )
    out = client.status()
    assert out["service"] == "myocr.app API"


@responses.activate
def test_usage_ok(client):
    responses.get(
        f"{BASE}/v1/usage",
        json={"success": True, "data": {
            "plan": "free", "calls_used": 42, "calls_limit": 100,
            "percentage": 42.0, "reset_date": "2026-06-01T00:00:00",
            "year_month": "2026-05", "is_test_key": False,
        }, "request_id": "r1"},
        status=200,
    )
    out = client.usage()
    assert out["calls_used"] == 42
    assert out["calls_limit"] == 100
    assert out["plan"] == "free"


# ---------- convert sync ----------

@responses.activate
def test_convert_xlsx(client, tmp_path):
    responses.post(
        f"{BASE}/v1/convert",
        body=b"FAKEXLSX",
        status=200,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        adding_headers={
            "X-MyOCR-Request-Id": "abc123",
            "X-MyOCR-Pages-Used": "3",
            "X-MyOCR-Model": "invoice",
        },
    )
    f = tmp_path / "in.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    result = client.convert(str(f), model="invoice")
    assert result.format == "xlsx"
    assert result.content == b"FAKEXLSX"
    assert result.pages_used == 3
    assert result.model == "invoice"

    out = tmp_path / "out.xlsx"
    result.save(str(out))
    assert out.read_bytes() == b"FAKEXLSX"


@responses.activate
def test_convert_txt(client, tmp_path):
    responses.post(
        f"{BASE}/v1/convert",
        body=b"plain text result",
        status=200,
        content_type="text/plain; charset=utf-8",
    )
    f = tmp_path / "in.pdf"
    f.write_bytes(b"x")
    result = client.convert(str(f), model="text")
    assert result.format == "txt"
    assert result.text() == "plain text result"


@responses.activate
def test_convert_json(client, tmp_path):
    responses.post(
        f"{BASE}/v1/convert",
        json={"success": True, "data": {"pages": 2, "tables": 1}, "request_id": "r2"},
        status=200,
    )
    f = tmp_path / "in.pdf"
    f.write_bytes(b"x")
    result = client.convert(str(f), model="tables", output="json")
    assert result.format == "json"
    assert result.json()["pages"] == 2


@responses.activate
def test_convert_invalid_api_key(client, tmp_path):
    responses.post(
        f"{BASE}/v1/convert",
        json={"success": False,
              "error": {"code": "INVALID_API_KEY", "message": "API key not found or revoked"},
              "request_id": "r3"},
        status=401,
    )
    f = tmp_path / "in.pdf"
    f.write_bytes(b"x")
    with pytest.raises(InvalidApiKey) as exc:
        client.convert(str(f), model="invoice")
    assert exc.value.status_code == 401
    assert exc.value.code == "INVALID_API_KEY"


@responses.activate
def test_convert_quota_exceeded(client, tmp_path):
    responses.post(
        f"{BASE}/v1/convert",
        json={"success": False, "error": {
            "code": "QUOTA_EXCEEDED",
            "message": "Monthly quota exceeded (50/50). Upgrade.",
            "upgrade_url": "https://myocr.app/account/api",
            "calls_used": 50,
            "calls_limit": 50,
            "reset_date": "2026-06-01T00:00:00",
            "current_plan": "free",
        }, "request_id": "r4"},
        status=402,
    )
    f = tmp_path / "in.pdf"
    f.write_bytes(b"x")
    with pytest.raises(QuotaExceeded) as exc:
        client.convert(str(f), model="invoice")
    assert exc.value.upgrade_url == "https://myocr.app/account/api"
    assert exc.value.calls_used == 50
    assert exc.value.current_plan == "free"


@responses.activate
def test_convert_file_too_large(client, tmp_path):
    responses.post(
        f"{BASE}/v1/convert",
        json={"success": False, "error": {"code": "FILE_TOO_LARGE", "message": "Max 5MB"},
              "request_id": "r5"},
        status=413,
    )
    f = tmp_path / "in.pdf"
    f.write_bytes(b"x")
    with pytest.raises(FileTooLarge):
        client.convert(str(f))


@responses.activate
def test_convert_unsupported_model(client, tmp_path):
    responses.post(
        f"{BASE}/v1/convert",
        json={"success": False, "error": {"code": "UNSUPPORTED_MODEL", "message": "..."},
              "request_id": "r6"},
        status=400,
    )
    f = tmp_path / "in.pdf"
    f.write_bytes(b"x")
    with pytest.raises(UnsupportedModel):
        client.convert(str(f), model="bogus")


@responses.activate
def test_convert_ocr_error(client, tmp_path):
    responses.post(
        f"{BASE}/v1/convert",
        json={"success": False, "error": {"code": "OCR_ERROR", "message": "..."},
              "request_id": "r7"},
        status=502,
    )
    f = tmp_path / "in.pdf"
    f.write_bytes(b"x")
    with pytest.raises(OcrEngineError):
        client.convert(str(f), model="invoice")


@responses.activate
def test_rate_limited(client, tmp_path):
    responses.post(
        f"{BASE}/v1/convert",
        json={"success": False, "error": {"code": "RATE_LIMITED", "message": "Slow down"},
              "request_id": "r8"},
        status=429,
    )
    f = tmp_path / "in.pdf"
    f.write_bytes(b"x")
    with pytest.raises(RateLimited):
        client.convert(str(f))


# ---------- jobs ----------

@responses.activate
def test_create_job(client, tmp_path):
    responses.post(
        f"{BASE}/v1/jobs",
        json={"success": True, "data": {"request_id": "job1", "status": "pending", "model": "invoice"},
              "request_id": "job1"},
        status=200,
    )
    f = tmp_path / "in.pdf"
    f.write_bytes(b"x")
    job = client.create_job(str(f), model="invoice", webhook_url="https://my.app/wh")
    assert job.request_id == "job1"
    assert job.status == JobStatus.PENDING
    assert job.model == "invoice"


@responses.activate
def test_get_job(client):
    responses.get(
        f"{BASE}/v1/jobs/job1",
        json={"success": True, "data": {
            "request_id": "job1", "status": "done", "model": "invoice",
            "pages_used": 5, "created_at": "2026-05-25T10:00:00",
            "completed_at": "2026-05-25T10:00:30",
        }, "request_id": "r"},
        status=200,
    )
    job = client.get_job("job1")
    assert job.is_done
    assert job.pages_used == 5


@responses.activate
def test_job_wait_polling(client):
    # 1st call: processing, 2nd call: done
    responses.get(
        f"{BASE}/v1/jobs/jX",
        json={"success": True, "data": {"request_id": "jX", "status": "processing", "model": "invoice"},
              "request_id": "r"},
        status=200,
    )
    responses.get(
        f"{BASE}/v1/jobs/jX",
        json={"success": True, "data": {"request_id": "jX", "status": "done", "model": "invoice", "pages_used": 2},
              "request_id": "r"},
        status=200,
    )
    job = Job(request_id="jX", status=JobStatus.PENDING, _client=client)
    job.wait(timeout=5.0, initial_delay=0.01, max_delay=0.05)
    assert job.is_done


@responses.activate
def test_get_job_result_signed_url(client):
    responses.get(
        f"{BASE}/v1/jobs/jY/result",
        json={"success": True, "data": {"result_url": "https://r2.example/out.xlsx", "expires_in": 86400},
              "request_id": "r"},
        status=200,
        content_type="application/json",
    )
    result = client.get_job_result("jY")
    assert result.result_url == "https://r2.example/out.xlsx"
    assert result.expires_in == 86400


@responses.activate
def test_get_job_result_not_ready(client):
    responses.get(
        f"{BASE}/v1/jobs/jZ/result",
        json={"success": False, "error": {"code": "NOT_READY", "message": "Job status=processing"},
              "request_id": "r"},
        status=409,
    )
    with pytest.raises(NotReady):
        client.get_job_result("jZ")


@responses.activate
def test_delete_job(client):
    responses.delete(
        f"{BASE}/v1/jobs/jW",
        json={"success": True, "data": {"request_id": "jW", "deleted": True}, "request_id": "r"},
        status=200,
    )
    out = client.delete_job("jW")
    assert out["deleted"] is True


@responses.activate
def test_job_not_found(client):
    responses.get(
        f"{BASE}/v1/jobs/missing",
        json={"success": False, "error": {"code": "NOT_FOUND", "message": "Job not found"},
              "request_id": "r"},
        status=404,
    )
    with pytest.raises(NotFound):
        client.get_job("missing")


# ---------- batch ----------

@responses.activate
def test_batch(client, tmp_path):
    responses.post(
        f"{BASE}/v1/batch",
        json={"success": True, "data": {
            "batch_id": "B1",
            "model": "invoice",
            "jobs_created": 2,
            "jobs": [
                {"filename": "a.pdf", "request_id": "j1", "status": "pending"},
                {"filename": "b.pdf", "request_id": "j2", "status": "pending"},
            ],
            "errors": [{"filename": "c.pdf", "code": "UNSUPPORTED_FILE_TYPE", "message": "ext"}],
        }, "request_id": "B1"},
        status=200,
    )
    a = tmp_path / "a.pdf"; a.write_bytes(b"x")
    b = tmp_path / "b.pdf"; b.write_bytes(b"y")
    result = client.batch([str(a), str(b)], model="invoice")
    assert result.batch_id == "B1"
    assert result.jobs_created == 2
    assert len(result.errors) == 1
    assert result.jobs[0].request_id == "j1"


# ---------- webhook signature ----------

def test_verify_webhook_signature_ok():
    body = b'{"event":"job.completed","data":{"request_id":"j1"}}'
    secret = "supersecret"
    import hashlib, hmac
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body, sig, secret) is True


def test_verify_webhook_signature_bad():
    body = b'{"event":"job.completed"}'
    secret = "supersecret"
    assert verify_webhook_signature(body, "sha256=000000", secret) is False
    assert verify_webhook_signature(body, "", secret) is False
    assert verify_webhook_signature(body, "sha256=abc", "") is False


def test_verify_webhook_signature_string_body():
    body_str = '{"event":"job.failed"}'
    secret = "k"
    import hashlib, hmac
    sig = "sha256=" + hmac.new(secret.encode(), body_str.encode(), hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body_str, sig, secret) is True


# ---------- input handling ----------

@responses.activate
def test_convert_accepts_bytes(client):
    responses.post(
        f"{BASE}/v1/convert",
        body=b"OK",
        status=200,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    result = client.convert(b"%PDF-1.4 fake", filename="my.pdf", model="invoice")
    assert result.content == b"OK"


@responses.activate
def test_convert_accepts_filelike(client, tmp_path):
    responses.post(
        f"{BASE}/v1/convert",
        body=b"OK",
        status=200,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    p = tmp_path / "x.pdf"
    p.write_bytes(b"x")
    with open(p, "rb") as fh:
        result = client.convert(fh, model="invoice")
    assert result.content == b"OK"


# ---------- env var fallback ----------

def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("MYOCR_API_KEY", "sk_live_envtest")
    c = MyOCRClient(base_url=BASE)
    assert c.api_key == "sk_live_envtest"


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("MYOCR_API_KEY", raising=False)
    from myocr_client.exceptions import MissingApiKey
    with pytest.raises(MissingApiKey):
        MyOCRClient(base_url=BASE)


@responses.activate
def test_rotate_key(client):
    responses.post(
        f"{BASE}/v1/keys/42/rotate",
        json={"success": True, "data": {
            "old_id": 42, "old_revoked": True,
            "id": 43, "key": "sk_live_NEW", "prefix": "sk_live_NE",
            "label": "main", "is_test": False,
            "created_at": "2026-05-26T10:00:00", "note": "store now",
        }, "request_id": "r"},
        status=200,
    )
    out = client.rotate_key(42)
    assert out["old_id"] == 42
    assert out["old_revoked"] is True
    assert out["key"] == "sk_live_NEW"


@responses.activate
def test_list_jobs(client):
    responses.get(
        f"{BASE}/v1/jobs",
        match=[matchers.query_param_matcher({"limit": "10", "offset": "0", "status": "done", "model": "invoice"})],
        json={"success": True, "data": {
            "total": 2, "limit": 10, "offset": 0,
            "jobs": [
                {"request_id": "j1", "status": "done", "model": "invoice", "pages_used": 3,
                 "created_at": "2026-05-26T10:00:00", "completed_at": "2026-05-26T10:00:30", "error_detail": None},
                {"request_id": "j2", "status": "done", "model": "invoice", "pages_used": 5,
                 "created_at": "2026-05-26T10:01:00", "completed_at": "2026-05-26T10:01:30", "error_detail": None},
            ],
        }, "request_id": "r"},
        status=200,
    )
    out = client.list_jobs(status="done", model="invoice", limit=10)
    assert out["total"] == 2
    assert len(out["jobs"]) == 2
    assert out["jobs"][0]["request_id"] == "j1"


@responses.activate
def test_batch_wait_all_parallel(client, tmp_path):
    # Setup batch creation
    responses.post(
        f"{BASE}/v1/batch",
        json={"success": True, "data": {
            "batch_id": "B1", "model": "invoice", "jobs_created": 2,
            "jobs": [
                {"filename": "a.pdf", "request_id": "j1", "status": "pending"},
                {"filename": "b.pdf", "request_id": "j2", "status": "pending"},
            ],
            "errors": [],
        }, "request_id": "B1"},
        status=200,
    )
    # Both jobs reach done on first poll
    responses.get(f"{BASE}/v1/jobs/j1",
                  json={"success": True, "data": {"request_id": "j1", "status": "done", "model": "invoice", "pages_used": 1}, "request_id": "r"})
    responses.get(f"{BASE}/v1/jobs/j2",
                  json={"success": True, "data": {"request_id": "j2", "status": "done", "model": "invoice", "pages_used": 2}, "request_id": "r"})

    a = tmp_path / "a.pdf"; a.write_bytes(b"x")
    b = tmp_path / "b.pdf"; b.write_bytes(b"y")
    result = client.batch([str(a), str(b)], model="invoice")
    done = result.wait_all(timeout=5.0, parallel=True, max_workers=2)
    assert all(j.is_done for j in done)
    assert len(done) == 2


# ---- page_range and fields: must be sent in the form, and omitted when empty ----

def _body_text(request):
    """Return the multipart body as text, to search it for the submitted fields."""
    body = request.body
    if hasattr(body, "read"):
        body = body.read()
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    return body


@responses.activate
def test_convert_sends_page_range_and_fields(client, tmp_path):
    responses.post(f"{BASE}/v1/convert", body=b"X", status=200,
                   content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    f = tmp_path / "in.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    client.convert(str(f), model="fields", page_range="1,3-5", fields=["number", "date", " "])
    body = _body_text(responses.calls[0].request)
    assert 'name="page_range"' in body and "1,3-5" in body
    assert 'name="fields"' in body and "number,date" in body


@responses.activate
def test_convert_omits_unset_page_range_and_fields(client, tmp_path):
    responses.post(f"{BASE}/v1/convert", body=b"X", status=200,
                   content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    f = tmp_path / "in.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    client.convert(str(f), model="tables")
    body = _body_text(responses.calls[0].request)
    assert 'name="page_range"' not in body
    assert 'name="fields"' not in body


@responses.activate
def test_job_and_batch_send_page_range(client, tmp_path):
    responses.post(f"{BASE}/v1/jobs",
                   json={"success": True, "data": {"request_id": "j9", "status": "pending"}, "request_id": "r"},
                   status=200)
    responses.post(f"{BASE}/v1/batch",
                   json={"success": True, "data": {"batch_id": "B9", "model": "invoice", "jobs_created": 1,
                                                   "jobs": [{"filename": "a.pdf", "request_id": "j9",
                                                             "status": "pending"}], "errors": []},
                         "request_id": "B9"},
                   status=200)
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    client.create_job(str(f), model="invoice", page_range="1")
    assert 'name="page_range"' in _body_text(responses.calls[0].request)
    client.batch([str(f)], model="invoice", page_range="2-")
    assert "2-" in _body_text(responses.calls[1].request)


@responses.activate
def test_batch_jobs_keep_their_filename(client, tmp_path):
    responses.post(f"{BASE}/v1/batch",
                   json={"success": True, "data": {"batch_id": "B1", "model": "tables", "jobs_created": 1,
                                                   "jobs": [{"filename": "b.pdf", "request_id": "j2", "status": "pending"}],
                                                   "errors": [{"filename": "a.pdf", "code": "UNSUPPORTED_FILE_TYPE", "message": "x"}]},
                         "request_id": "B1"},
                   status=200)
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    a.write_bytes(b"%PDF-1.4 fake"); b.write_bytes(b"%PDF-1.4 fake")
    result = client.batch([str(a), str(b)], model="tables")
    assert [j.filename for j in result.jobs] == ["b.pdf"]
    assert result.errors[0]["filename"] == "a.pdf"


def test_version_matches_pyproject():
    import pathlib
    import re
    from myocr_client import __version__
    pyproject = (pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
    assert re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1) == __version__
