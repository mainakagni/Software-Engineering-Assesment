import uuid
from app.models.document import Document


def test_cross_user_isolation(client, db, user_a, user_b, auth_headers_user_a, auth_headers_user_b):
    """
    CRITICAL SECURITY TEST:
    Proves User B cannot access, read, or delete User A's documents,
    even if User B knows User A's document ID.
    """
    # 1. Create a document owned by User A
    doc_a = Document(
        id=uuid.uuid4(),
        user_id=user_a.id,
        filename="secret_user_a_file.pdf",
        file_type="pdf",
        file_size=1024,
        status="ready"
    )
    db.add(doc_a)
    db.commit()

    # 2. User A can list and retrieve their own document
    res_a_list = client.get("/api/v1/documents", headers=auth_headers_user_a)
    assert res_a_list.status_code == 200
    doc_ids_a = [d["id"] for d in res_a_list.json()]
    assert str(doc_a.id) in doc_ids_a

    res_a_get = client.get(f"/api/v1/documents/{doc_a.id}", headers=auth_headers_user_a)
    assert res_a_get.status_code == 200
    assert res_a_get.json()["filename"] == "secret_user_a_file.pdf"

    # 3. User B's list should NOT contain User A's document
    res_b_list = client.get("/api/v1/documents", headers=auth_headers_user_b)
    assert res_b_list.status_code == 200
    doc_ids_b = [d["id"] for d in res_b_list.json()]
    assert str(doc_a.id) not in doc_ids_b

    # 4. User B attempts to access User A's document by guessing ID -> MUST return 404
    res_b_get = client.get(f"/api/v1/documents/{doc_a.id}", headers=auth_headers_user_b)
    assert res_b_get.status_code == 404

    # 5. User B attempts to delete User A's document -> MUST return 404 and NOT delete
    res_b_del = client.delete(f"/api/v1/documents/{doc_a.id}", headers=auth_headers_user_b)
    assert res_b_del.status_code == 404

    # Verify document still exists for User A
    doc_still_exists = db.query(Document).filter(Document.id == doc_a.id).first()
    assert doc_still_exists is not None
