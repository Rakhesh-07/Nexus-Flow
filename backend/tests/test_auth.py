import pytest

def test_register_user(client):
    response = client.post(
        "/register",
        json={"username": "testuser", "password": "testpassword123"}
    )
    assert response.status_code == 201
    assert response.json()["message"] == "User registered successfully"
    assert "id" in response.json()

def test_register_duplicate_user(client):
    # First registration
    client.post(
        "/register",
        json={"username": "dupuser", "password": "password123"}
    )
    # Second registration with same username
    response = client.post(
        "/register",
        json={"username": "dupuser", "password": "password456"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already registered"

def test_login_success(client):
    # Register user
    client.post(
        "/register",
        json={"username": "loginuser", "password": "loginpassword"}
    )
    # Login
    response = client.post(
        "/login",
        data={"username": "loginuser", "password": "loginpassword"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"

def test_login_incorrect_credentials(client):
    response = client.post(
        "/login",
        data={"username": "nonexistentuser", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"
