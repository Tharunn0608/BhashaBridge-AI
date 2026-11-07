"""Shared helpers for calling the Gnani (Vachana) REST APIs.

Error formats below follow the official Gnani error reference:
https://docs.gnani.ai/api/introduction/errors.md
"""
import logging
import time

import requests

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class GnaniError(Exception):
    """A problem talking to Gnani, with a message that is safe to show users."""

    def __init__(self, message, *, code="GNANI_ERROR", http_status=502, upstream_status=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status          # status WE return to the browser
        self.upstream_status = upstream_status  # status Gnani returned (if any)


def extract_error(resp):
    """Return (code, message) from any of the documented Gnani error shapes."""
    code = f"HTTP_{resp.status_code}"
    message = ""
    try:
        body = resp.json()
    except ValueError:
        body = None

    if isinstance(body, dict):
        err, detail = body.get("error"), body.get("detail")
        if isinstance(err, dict):                       # STT envelope
            code = err.get("type", code)
            message = err.get("message", "")
        elif isinstance(err, str):                      # 504 timeout body
            code = body.get("code", code)
            message = body.get("message") or err
        elif isinstance(detail, dict):                  # auth / rate limit
            code = detail.get("error_code", code)
            message = detail.get("message", "")
        elif isinstance(detail, list) and detail:       # 422 validation
            first = detail[0]
            if isinstance(first, dict):
                loc = ".".join(str(x) for x in first.get("loc", []))
                message = f"{first.get('msg', 'Invalid request')} ({loc})"
            else:
                message = str(first)
            code = "VALIDATION_ERROR"
        elif isinstance(body.get("message"), str):      # flat TTS error
            message = body["message"]
    if not message:
        message = (resp.text or "")[:200]
    return code, message


def raise_for_response(resp, service: str):
    """Turn a non-2xx Gnani response into a friendly GnaniError."""
    code, upstream_msg = extract_error(resp)
    status = resp.status_code
    if status == 401:
        msg = ("Gnani rejected the API key (missing or invalid). "
               "Check GNANI_API_KEY in your .env file.")
        out = 502
    elif status == 402:
        msg = "Your Gnani account has insufficient credits for this request."
        out = 502
    elif status == 403:
        msg = ("Gnani refused the request: your key may lack access to the "
               f"{service} service or have no credits left.")
        out = 502
    elif status == 429:
        msg = "Gnani is rate limiting requests. Wait a moment and try again."
        out = 429
    elif status in (400, 422):
        msg = f"{service} could not process this request: {upstream_msg}"
        out = 422
    elif status == 504:
        msg = f"{service} timed out. Please try again."
        out = 504
    else:
        msg = f"The Gnani {service} service is temporarily unavailable. Please try again."
        out = 502
    raise GnaniError(msg, code=code, http_status=out, upstream_status=status)


def request_with_retry(method, url, *, retries=1, backoff=0.6, service="API", **kwargs):
    """requests.request with a small retry for rate limits / transient errors.

    Pass file contents as bytes (not open file handles) so retries can resend them.
    Never logs headers, so the API key cannot leak into logs.
    """
    last_exc = None
    for attempt in range(retries + 1):
        started = time.time()
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.Timeout as exc:
            last_exc = GnaniError(f"{service} timed out. Please try again.",
                                  code="TIMEOUT", http_status=504)
            log.warning("%s timeout (attempt %d)", service, attempt + 1)
        except requests.ConnectionError as exc:
            last_exc = GnaniError(
                f"Could not reach the Gnani {service} service. Check your internet connection.",
                code="CONNECTION_ERROR", http_status=502)
            log.warning("%s connection error (attempt %d)", service, attempt + 1)
        else:
            log.info("%s -> HTTP %s in %.2fs", service, resp.status_code, time.time() - started)
            if resp.status_code in RETRYABLE_STATUS and attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            return resp
        if attempt < retries:
            time.sleep(backoff * (2 ** attempt))
    raise last_exc
