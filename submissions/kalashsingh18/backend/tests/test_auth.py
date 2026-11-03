from app.utils.security import hash_password, verify_password


def test_password_hashing():
    raw_pass = "SecurePass123!"
    hashed = hash_password(raw_pass)
    assert hashed != raw_pass
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_signup_and_login_flow(client):
    signup_res = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "Password123!"
        }
    )
    assert signup_res.status_code == 201
    token_data = signup_res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["user"]["username"] == "newuser"

    # 2. Login with valid credentials
    login_res = client.post(
        "/api/v1/auth/login",
        json={
            "username_or_email": "newuser",
            "password": "Password123!"
        }
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

    # 3. Login with invalid password
    bad_login = client.post(
        "/api/v1/auth/login",
        json={
            "username_or_email": "newuser",
            "password": "WrongPassword!"
        }
    )
    assert bad_login.status_code == 401

    # 4. Access /me with token
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "newuser@example.com"
