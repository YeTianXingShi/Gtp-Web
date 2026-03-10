from __future__ import annotations

import json
from pathlib import Path


def test_admin_page_requires_admin(logged_in_client):
    resp = logged_in_client.get("/admin", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/chat")



def test_admin_api_requires_admin(logged_in_client):
    resp = logged_in_client.get("/api/admin/users")
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["ok"] is False



def test_admin_can_manage_users_and_config_files(admin_client, app):
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

    files_resp = admin_client.get("/api/admin/config-files")
    assert files_resp.status_code == 200
    files_data = files_resp.get_json()
    assert files_data["default_file_id"] == "auth_users"
    file_ids = [item["id"] for item in files_data["files"]]
    assert file_ids == ["auth_users", "app_env"]

    auth_config_resp = admin_client.get("/api/admin/config-files/auth_users")
    assert auth_config_resp.status_code == 200
    auth_config_data = auth_config_resp.get_json()
    parsed = json.loads(auth_config_data["content"])
    assert any(item["username"] == "bob" and item["is_admin"] for item in parsed["users"])
    assert auth_config_data["requires_restart"] is False

    env_config_resp = admin_client.get("/api/admin/config-files/app_env")
    assert env_config_resp.status_code == 200
    env_config_data = env_config_resp.get_json()
    assert env_config_data["requires_restart"] is True
    assert "AI_BASE_URL=https://example.invalid/v1" in env_config_data["content"]

    save_env_resp = admin_client.put(
        "/api/admin/config-files/app_env",
        json={"content": "AI_BASE_URL=https://new.example/v1\nAI_API_KEY=new-key\nAI_MODELS=gpt-4o-mini\n"},
    )
    assert save_env_resp.status_code == 200
    env_file = Path(app.config["ENV_FILE"])
    assert "AI_BASE_URL=https://new.example/v1" in env_file.read_text(encoding="utf-8")

    rewritten = {
        "users": [
            {"username": "admin", "password": "admin-pass", "is_admin": True},
            {"username": "u", "password": "p", "is_admin": False},
            {"username": "ops", "password": "ops-pass", "is_admin": False},
        ]
    }
    save_auth_resp = admin_client.put(
        "/api/admin/config-files/auth_users",
        json={"content": json.dumps(rewritten, ensure_ascii=False, indent=2)},
    )
    assert save_auth_resp.status_code == 200

    delete_resp = admin_client.delete("/api/admin/users/ops")
    assert delete_resp.status_code == 200

    final_list_resp = admin_client.get("/api/admin/users")
    assert final_list_resp.status_code == 200
    final_usernames = [item["username"] for item in final_list_resp.get_json()["users"]]
    assert final_usernames == ["admin", "u"]
