import pytest
from database.models import User, Document, AuditLog
from services.permission_service import PermissionService, ROLE_CLEARANCE_MATRIX, CLASSIFICATIONS

def test_clearance_matrix():
    guest = User(username="guest", role="guest", clearance_level="PUBLIC", is_active=True)
    emp = User(username="emp", role="employee", clearance_level="INTERNAL", is_active=True)
    lead = User(username="lead", role="team_lead", clearance_level="CONFIDENTIAL", is_active=True)
    mgr = User(username="mgr", role="department_manager", clearance_level="RESTRICTED", is_active=True)
    admin = User(username="admin", role="super_admin", clearance_level="HIGHLY_CONFIDENTIAL", is_active=True)

    assert PermissionService.get_allowed_classifications(guest) == ["PUBLIC"]
    assert "INTERNAL" in PermissionService.get_allowed_classifications(emp)
    assert "CONFIDENTIAL" in PermissionService.get_allowed_classifications(lead)
    assert "RESTRICTED" in PermissionService.get_allowed_classifications(mgr)
    assert len(PermissionService.get_allowed_classifications(admin)) == 5


def test_can_upload_permission():
    guest = User(username="guest", role="guest", is_active=True)
    emp = User(username="emp", role="employee", is_active=True)
    
    assert PermissionService.can_upload_document(guest) == False
    assert PermissionService.can_upload_document(emp) == True


def test_chroma_filter_construction():
    emp = User(username="emp", role="employee", department="Finance", clearance_level="INTERNAL", is_active=True)
    filter_dict = PermissionService.build_chroma_filter(emp)
    
    assert "$and" in filter_dict
    conditions = filter_dict["$and"]
    assert {"approved": True} in conditions


def test_guest_upload_blocked(client):
    # Register & Login Guest
    client.post("/register", json={
        "username": "testguest",
        "password": "Password123!",
        "department": "Operations",
        "role": "guest"
    })
    login_res = client.post("/login", data={"username": "testguest", "password": "Password123!"})
    token = login_res.json()["access_token"]

    # Upload attempt
    files = {"file": ("test.txt", b"Test content", "text/plain")}
    data = {"department": "Operations", "classification": "PUBLIC"}
    res = client.post("/upload", files=files, data=data, headers={"Authorization": f"Bearer {token}"})
    
    assert res.status_code == 403


def test_department_isolation_and_approval(client):
    # Register Finance Manager
    client.post("/register", json={
        "username": "testfinmgr",
        "password": "Password123!",
        "department": "Finance",
        "role": "department_manager"
    })
    fin_login = client.post("/login", data={"username": "testfinmgr", "password": "Password123!"})
    fin_token = fin_login.json()["access_token"]

    # Upload Approved Finance Document
    files = {"file": ("fin_budget.txt", b"Finance Quarterly Budget $5,000,000", "text/plain")}
    data = {"department": "Finance", "classification": "CONFIDENTIAL", "visibility": "Department"}
    upload_res = client.post("/upload", files=files, data=data, headers={"Authorization": f"Bearer {fin_token}"})
    assert upload_res.status_code == 200
    assert upload_res.json()["approved"] == True

    # Register HR Employee
    client.post("/register", json={
        "username": "testhremp",
        "password": "Password123!",
        "department": "Human Resources",
        "role": "employee"
    })
    hr_login = client.post("/login", data={"username": "testhremp", "password": "Password123!"})
    hr_token = hr_login.json()["access_token"]

    # HR Employee query for Finance budget
    query_res = client.post("/query", json={"query": "Finance Quarterly Budget"}, headers={"Authorization": f"Bearer {hr_token}"})
    assert query_res.status_code == 200
    
    # Verify citations do NOT contain fin_budget.txt for HR Employee
    citations = query_res.json()["response"].get("citations", [])
    assert "fin_budget.txt" not in citations
