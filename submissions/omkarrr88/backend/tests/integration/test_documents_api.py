from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import DocumentBlob, IngestionJob
from app.main import create_app
from tests.conftest import make_test_settings, signup
from tests.pdf_factory import make_pdf


def upload(
    client: TestClient,
    headers: dict[str, str],
    name: str = "policy.txt",
    data: bytes = b"Hotel stays are reimbursed up to 180 dollars a night.",
) -> dict:
    response = client.post("/api/documents", headers=headers, files={"file": (name, data)})
    assert response.status_code == 202, response.text
    return response.json()["data"]


@pytest.fixture
def small_limits_client(db: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(make_test_settings(max_documents_per_user=2, max_upload_mb=1))
    app.state.session_factory = db
    with TestClient(app) as client:
        yield client


def test_upload_is_accepted_and_queued(client: TestClient, db: sessionmaker[Session]) -> None:
    headers = signup(client)
    response = client.post(
        "/api/documents",
        headers={**headers, "X-Request-ID": "upload-req-1"},
        files={"file": ("Travel Policy.pdf", make_pdf(["Per diem is 75 dollars."]))},
    )
    body = response.json()["data"]
    assert response.status_code == 202
    assert body["status"] == "queued"
    assert (body["filename"], body["content_type"]) == ("Travel Policy.pdf", "application/pdf")
    assert body["size_bytes"] > 0
    assert body["chunk_count"] is None

    with db() as session:
        job = session.scalars(select(IngestionJob)).one()
        assert (job.status, job.request_id) == ("queued", "upload-req-1")
        assert session.scalar(select(DocumentBlob.data)) is not None


def test_list_get_and_delete(client: TestClient) -> None:
    headers = signup(client)
    first = upload(client, headers, "a.txt", b"first file")
    second = upload(client, headers, "b.md", b"# second file")

    listing = client.get("/api/documents", headers=headers).json()
    assert [d["id"] for d in listing["data"]] == [second["id"], first["id"]]  # newest first
    assert listing["meta"] == {"total": 2, "limit": 50, "offset": 0}

    page = client.get("/api/documents?limit=1&offset=1", headers=headers).json()
    assert [d["id"] for d in page["data"]] == [first["id"]]

    assert client.get(f"/api/documents/{first['id']}", headers=headers).json()["data"] == first
    assert client.delete(f"/api/documents/{first['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/documents/{first['id']}", headers=headers).status_code == 404
    assert client.get("/api/documents", headers=headers).json()["meta"]["total"] == 1


def test_other_users_documents_are_invisible(client: TestClient) -> None:
    alice = signup(client, "alice@example.com")
    bob = signup(client, "bob@example.com")
    document = upload(client, alice)

    assert client.get(f"/api/documents/{document['id']}", headers=bob).status_code == 404
    assert client.delete(f"/api/documents/{document['id']}", headers=bob).status_code == 404
    assert client.get("/api/documents", headers=bob).json()["data"] == []
    # still there for its owner
    assert client.get(f"/api/documents/{document['id']}", headers=alice).status_code == 200


def test_the_same_file_twice_is_a_conflict_but_another_user_may_upload_it(
    client: TestClient,
) -> None:
    alice = signup(client, "alice@example.com")
    upload(client, alice, "one.txt", b"same bytes")
    again = client.post("/api/documents", headers=alice, files={"file": ("two.txt", b"same bytes")})
    assert again.status_code == 409
    assert again.json()["error"]["message"] == "You have already uploaded this file."
    upload(client, signup(client, "bob@example.com"), "one.txt", b"same bytes")


def test_document_limit(small_limits_client: TestClient) -> None:
    headers = signup(small_limits_client)
    upload(small_limits_client, headers, "1.txt", b"one")
    upload(small_limits_client, headers, "2.txt", b"two")
    third = small_limits_client.post(
        "/api/documents", headers=headers, files={"file": ("3.txt", b"three")}
    )
    assert third.status_code == 409
    assert "limit of 2 documents" in third.json()["error"]["message"]


def test_oversized_upload_is_rejected_before_it_is_read(small_limits_client: TestClient) -> None:
    headers = signup(small_limits_client)
    big = b"x" * (2 * 1024 * 1024)
    response = small_limits_client.post(
        "/api/documents", headers=headers, files={"file": ("big.txt", big)}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert response.headers["X-Request-ID"]


def test_file_just_over_the_limit_is_caught_after_parsing(small_limits_client: TestClient) -> None:
    headers = signup(small_limits_client)
    data = b"x" * (1024 * 1024 + 10)  # within the multipart allowance, over the file limit
    response = small_limits_client.post(
        "/api/documents", headers=headers, files={"file": ("edge.txt", data)}
    )
    assert response.status_code == 413


def test_upload_without_content_length_is_refused(client: TestClient) -> None:
    headers = signup(client)

    def body() -> Iterator[bytes]:
        yield b"--x\r\nContent-Disposition: form-data; name=file; filename=a.txt\r\n\r\nhi\r\n--x--"

    response = client.post(
        "/api/documents",
        headers={**headers, "Content-Type": "multipart/form-data; boundary=x"},
        content=body(),
    )
    assert response.status_code == 411


@pytest.mark.parametrize(
    ("name", "data", "status"),
    [
        ("slides.pptx", b"PK\x03\x04", 415),
        ("fake.pdf", b"not a pdf", 415),
        ("empty.txt", b"", 422),
    ],
)
def test_bad_files_are_rejected(client: TestClient, name: str, data: bytes, status: int) -> None:
    headers = signup(client)
    response = client.post("/api/documents", headers=headers, files={"file": (name, data)})
    assert response.status_code == status
    assert client.get("/api/documents", headers=headers).json()["meta"]["total"] == 0


def test_missing_file_field_is_a_validation_error(client: TestClient) -> None:
    response = client.post("/api/documents", headers=signup(client), data={"other": "x"})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "file"


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "limit=abc"])
def test_list_validates_paging(client: TestClient, query: str) -> None:
    assert client.get(f"/api/documents?{query}", headers=signup(client)).status_code == 422


def test_bad_document_id_is_a_validation_error(client: TestClient) -> None:
    assert client.get("/api/documents/not-a-uuid", headers=signup(client)).status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/documents"),
        ("post", "/api/documents"),
        ("get", "/api/documents/00000000-0000-0000-0000-000000000000"),
        ("delete", "/api/documents/00000000-0000-0000-0000-000000000000"),
    ],
)
def test_documents_require_login(client: TestClient, method: str, path: str) -> None:
    response = client.request(
        method, path, files={"file": ("a.txt", b"x")} if method == "post" else None
    )
    assert response.status_code == 401
