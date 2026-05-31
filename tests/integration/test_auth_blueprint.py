from __future__ import annotations

import time

import jwt


def test_login_html_page_removed(client):
    """旧 GET /login HTML 路由已下线；改由 SPA 兜底（dist 不存在则 503）。"""
    resp = client.get("/login")
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        assert resp.mimetype == "text/html"


def test_login_success_returns_jwt(client):
    resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["user"]["username"] == "u"
    assert data["user"]["is_admin"] is False
    assert isinstance(data["access_token"], str) and data["access_token"]
    assert data["expires_in"] > 0
    # refresh 必须通过 HttpOnly Cookie 下发，不在 body
    cookie_header = resp.headers.get("Set-Cookie", "")
    assert "gtp_refresh=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Path=/api" in cookie_header


def test_admin_login_success(client):
    resp = client.post("/api/login", json={"username": "admin", "password": "admin-pass"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user"]["is_admin"] is True


def test_login_failure(client):
    resp = client.post("/api/login", json={"username": "u", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False


def test_login_missing_fields(client):
    resp = client.post("/api/login", json={"username": "", "password": ""})
    assert resp.status_code == 400


def test_me_requires_login(client):
    resp = client.get("/api/me")
    assert resp.status_code == 401


def test_me_returns_user(logged_in_client):
    resp = logged_in_client.get("/api/me")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user"]["username"] == "u"
    assert data["user"]["is_admin"] is False


def test_refresh_with_cookie(client):
    login_resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert login_resp.status_code == 200

    refresh_resp = client.post("/api/refresh")
    assert refresh_resp.status_code == 200
    data = refresh_resp.get_json()
    assert data["ok"] is True
    assert isinstance(data["access_token"], str)
    assert data["user"]["username"] == "u"


def test_refresh_without_cookie(client):
    resp = client.post("/api/refresh")
    assert resp.status_code == 401


def test_refresh_token_rotated_old_revoked(client, app):
    """轮转后旧 refresh 应被加入撤销列表，重放将失败。"""
    login_resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert login_resp.status_code == 200
    # 抓取首张 refresh cookie 的值
    set_cookie = login_resp.headers.get("Set-Cookie", "")
    old_refresh = set_cookie.split("gtp_refresh=", 1)[1].split(";", 1)[0]

    # 使用 cookie 调 refresh，触发轮转
    refresh_resp = client.post("/api/refresh")
    assert refresh_resp.status_code == 200

    # 此时 cookie jar 已经被轮转后的新 refresh 覆盖。
    # 用「旧 refresh」直接 PUT 到 cookie 上模拟攻击者重放
    client.delete_cookie("gtp_refresh", path="/api")
    client.set_cookie("gtp_refresh", old_refresh, path="/api")
    replay_resp = client.post("/api/refresh")
    assert replay_resp.status_code == 401


def test_logout_revokes_refresh(client):
    login_resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert login_resp.status_code == 200

    logout_resp = client.post("/api/logout")
    assert logout_resp.status_code == 200

    # 登出后 refresh 已撤销，再调用 refresh 应失败
    refresh_resp = client.post("/api/refresh")
    assert refresh_resp.status_code == 401


def test_access_token_payload(logged_in_client, app):
    """access token 应包含 sub、is_admin、type=access。"""
    payload = jwt.decode(
        logged_in_client.access_token,
        app.config["JWT_SECRET"],
        algorithms=["HS256"],
    )
    assert payload["sub"] == "u"
    assert payload["is_admin"] is False
    assert payload["type"] == "access"
    assert payload["exp"] > int(time.time())


def test_invalid_token_rejected(client):
    resp = client.get("/api/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401
