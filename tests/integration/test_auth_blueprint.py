from __future__ import annotations


def test_login_page_accessible(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_login_success(client):
    resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_login_failure(client):
    resp = client.post("/api/login", json={"username": "u", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False
