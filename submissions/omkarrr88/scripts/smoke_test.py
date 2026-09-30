"""End-to-end check of a running stack: sign up, upload, wait for processing, ask, read history.

Uses only the standard library, so it runs on any machine with Python 3.10+:

    python scripts/smoke_test.py http://localhost:8000

Run it against a stack started with the offline providers (LLM_PROVIDER=fake and
EMBEDDING_PROVIDER=fake) or with real Gemini keys; both must answer the question below.
"""

import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

DOCUMENT = b"""# Travel policy

## Flights
Domestic flights must be booked at least 7 business days before departure.
International flights must be booked at least 14 business days before departure.

## Hotels
Hotel stays are reimbursed up to 180 dollars per night.
"""
QUESTION = "How many business days before departure must international flights be booked?"
TIMEOUT_SECONDS = 120


def call(
    base: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(base + path, data=body, method=method)  # noqa: S310
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")
    except (urllib.error.URLError, ConnectionError):  # not listening yet
        return 0, {}


def multipart(field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
    )
    tail = f"\r\n--{boundary}--\r\n"
    return head.encode() + data + tail.encode(), f"multipart/form-data; boundary={boundary}"


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL: {message}")
        sys.exit(1)
    print(f"ok: {message}")


def wait_until(predicate: Any, what: str) -> Any:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(2)
    check(False, f"{what} within {TIMEOUT_SECONDS} s")
    return None


def main(base: str) -> None:
    base = base.rstrip("/")
    if not base.startswith(("http://", "https://")):  # urllib would also open file: URLs
        sys.exit(f"not an http(s) URL: {base}")
    wait_until(lambda: call(base, "GET", "/health")[0] == 200, "the API and the worker are healthy")

    email = f"smoke-{uuid.uuid4().hex[:12]}@example.com"
    credentials = json.dumps({"email": email, "password": "smoke-test-password"}).encode()
    status, body = call(
        base, "POST", "/api/auth/signup", body=credentials, content_type="application/json"
    )
    check(status == 201, f"sign up ({status})")
    token = body["data"]["access_token"]

    payload, content_type = multipart("file", "travel-policy.md", DOCUMENT)
    status, body = call(
        base, "POST", "/api/documents", token=token, body=payload, content_type=content_type
    )
    check(status == 202, f"upload accepted ({status})")
    document_id = body["data"]["id"]

    def ready() -> bool:
        _, document = call(base, "GET", f"/api/documents/{document_id}", token=token)
        if document["data"]["status"] == "failed":
            check(False, f"the document is processed (it failed: {document['data']['error']})")
        return bool(document["data"]["status"] == "ready")

    wait_until(ready, "the document is processed")

    question = json.dumps({"question": QUESTION}).encode()
    status, body = call(
        base, "POST", "/api/questions", token=token, body=question, content_type="application/json"
    )
    check(status == 200, f"question answered ({status})")
    answer = body["data"]
    check(answer["found"] is True, f"answer found: {answer['answer']!r}")
    check("14" in answer["answer"], "the answer has the right number of days")
    check(
        any(c["document_id"] == document_id and c["quote_verified"] for c in answer["citations"]),
        "the answer cites the uploaded document with a verified quote",
    )

    status, body = call(base, "GET", "/api/questions", token=token)
    check(status == 200 and body["meta"]["total"] == 1, "the question is in the history")

    status, _ = call(base, "DELETE", f"/api/documents/{document_id}", token=token)
    check(status == 204, f"document deleted ({status})")
    print("smoke test passed")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000")
