import pytest

def test_workflow_execution_success(client):
    # Register and login user to get credentials
    client.post(
        "/register",
        json={"username": "workflowuser", "password": "securepassword"}
    )
    login_res = client.post(
        "/login",
        data={"username": "workflowuser", "password": "securepassword"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Query endpoint
    query_payload = {
        "query": "Compare sales records from last year using Python executor and list recommendations.",
        "conversation_id": None
    }
    
    response = client.post("/query", json=query_payload, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert "conversation_id" in res_data
    assert "execution_id" in res_data
    assert "status" in res_data
    assert "response" in res_data
    assert "structured_answer" in res_data["response"]
    assert "explanation" in res_data["response"]
    assert "citations" in res_data["response"]
    assert "recommendations" in res_data["response"]
    assert "execution_time_ms" in res_data

import uuid

def test_get_history_success(client):
    # Register and login
    client.post(
        "/register",
        json={"username": "historyuser", "password": "securepassword"}
    )
    login_res = client.post(
        "/login",
        data={"username": "historyuser", "password": "securepassword"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Run a quick query with a unique UUID to bypass the semantic cache
    unique_query = f"Run a test log inquiry {uuid.uuid4()}"
    client.post(
        "/query",
        json={"query": unique_query, "conversation_id": None},
        headers=headers
    )
    
    # Retrieve history
    response = client.get("/workflow/history", headers=headers)
    assert response.status_code == 200
    history = response.json()
    assert len(history) > 0
    assert "query" in history[0]
    assert "status" in history[0]
    assert "steps_taken" in history[0]

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "healthy"
    
def test_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
