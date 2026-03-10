from __future__ import annotations

import json


def test_admin_page_requires_admin(logged_in_client):
    resp = logged_in_client.get("/admin", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/chat")



def test_admin_api_requires_admin(logged_in_client):
    resp = logged_in_client.get("/api/admin/users")
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["ok"] is False



def test_admin_can_manage_users_and_auth_config(admin_client):
    page_resp = admin_client.get("/admin")
    assert page_resp.status_code == 200

    list_resp = admin_client.get("/api/admin/users")
    assert list_resp.status_code == 200
    usernames = [item["username"] for item in list_resp.get_json()["users"]]
    assert usernames == ["admin", "u"]

    create_resp = admin_client.post(
        "/api/admin/users",
        json={"username": "bob", "password": "bob-pass", "is_admin": False},
    )
    assert create_resp.status_code == 201
    assert create_resp.get_json()["user"]["username"] == "bob"

    update_resp = admin_client.patch(
        "/api/admin/users/bob",
        json={"is_admin": True, "password": "bob-pass-2"},
    )
    assert update_resp.status_code == 200
    assert update_resp.get_json()["user"]["is_admin"] is True

    config_resp = admin_client.get("/api/admin/auth-config")
    assert config_resp.status_code == 200
    config_data = config_resp.get_json()
    parsed = json.loads(config_data["content"])
    assert any(item["username"] == "bob" and item["is_admin"] for item in parsed["users"])

    rewritten = {
        "users": [
            {"username": "admin", "password": "admin-pass", "is_admin": True},
            {"username": "u", "password": "p", "is_admin": False},
            {"username": "ops", "password": "ops-pass", "is_admin": False},
        ]
    }
    save_resp = admin_client.put(
        "/api/admin/auth-config",
        json={"content": json.dumps(rewritten, ensure_ascii=False, indent=2)},
    )
    assert save_resp.status_code == 200

    delete_resp = admin_client.delete("/api/admin/users/ops")
    assert delete_resp.status_code == 200

    final_list_resp = admin_client.get("/api/admin/users")
    assert final_list_resp.status_code == 200
    final_usernames = [item["username"] for item in final_list_resp.get_json()["users"]]
    assert final_usernames == ["admin", "u"]
