from __future__ import annotations


def test_login_page_accessible(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_login_success(client):
    resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["is_admin"] is False
    assert data["redirect_to"] == "/chat"


def test_admin_login_success(client):
    resp = client.post("/api/login", json={"username": "admin", "password": "admin-pass"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["is_admin"] is True
    assert data["redirect_to"] == "/admin"


def test_login_failure(client):
    resp = client.post("/api/login", json={"username": "u", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False
