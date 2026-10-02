"""
Document endpoint tests — upload, list, isolation
"""
import io
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_documents_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/documents", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_upload_text_document(client: AsyncClient, auth_headers: dict):
    content = b"This is a test document about machine learning and neural networks."
    resp = await client.post(
        "/api/v1/documents",
        headers=auth_headers,
        files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["original_filename"] == "test.txt"


@pytest.mark.asyncio
async def test_upload_unsupported_type(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/documents",
        headers=auth_headers,
        files={"file": ("test.exe", io.BytesIO(b"binary"), "application/octet-stream")},
    )
    assert resp.status_code in (415, 422)


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_user_isolation(
    client: AsyncClient,
    auth_headers: dict,
    second_auth_headers: dict,
):
    """User A cannot access User B's documents — critical security test."""
    # Upload as user A
    content = b"User A's private document."
    upload_resp = await client.post(
        "/api/v1/documents",
        headers=auth_headers,
        files={"file": ("private.txt", io.BytesIO(content), "text/plain")},
    )
    assert upload_resp.status_code == 202
    doc_id = upload_resp.json()["id"]

    # User B tries to access User A's document
    resp = await client.get(f"/api/v1/documents/{doc_id}", headers=second_auth_headers)
    assert resp.status_code == 404  # Must not reveal it exists

    # User B list should not contain User A's document
    list_resp = await client.get("/api/v1/documents", headers=second_auth_headers)
    doc_ids = [d["id"] for d in list_resp.json()["items"]]
    assert doc_id not in doc_ids


@pytest.mark.asyncio
async def test_delete_own_document(client: AsyncClient, auth_headers: dict):
    content = b"Document to delete."
    upload = await client.post(
        "/api/v1/documents",
        headers=auth_headers,
        files={"file": ("todelete.txt", io.BytesIO(content), "text/plain")},
    )
    doc_id = upload.json()["id"]
    delete_resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    # Verify gone
    get_resp = await client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert get_resp.status_code == 404
