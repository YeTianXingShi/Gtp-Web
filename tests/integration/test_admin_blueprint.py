from __future__ import annotations

import json
from pathlib import Path


def test_admin_page_requires_admin(logged_in_client):
    resp = logged_in_client.get("/admin", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/chat")



def test_admin_api_requires_admin(logged_in_client):
    resp = logged_in_client.get("/api/admin/config-files")
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["ok"] is False



def test_admin_can_edit_config_files_and_hot_reload_env(admin_client, app):
    page_resp = admin_client.get("/admin")
    assert page_resp.status_code == 200
    page_text = page_resp.get_data(as_text=True)
    assert "配置文件管理" in page_text
    assert "用户管理" not in page_text
    assert "create-user-form" not in page_text

    files_resp = admin_client.get("/api/admin/config-files")
    assert files_resp.status_code == 200
    files_data = files_resp.get_json()
    assert files_data["default_file_id"] == "auth_users"
    file_ids = [item["id"] for item in files_data["files"]]
    assert file_ids == ["auth_users", "app_env"]

    auth_config_resp = admin_client.get("/api/admin/config-files/auth_users")
    assert auth_config_resp.status_code == 200
    auth_config_data = auth_config_resp.get_json()
    parsed_auth = json.loads(auth_config_data["content"])
    assert [item["username"] for item in parsed_auth["users"]] == ["admin", "u"]
    assert auth_config_data["requires_restart"] is False

    rewritten_auth = {
        "users": [
            {"username": "admin", "password": "admin-pass", "is_admin": True},
            {"username": "u", "password": "p", "is_admin": False},
            {"username": "ops", "password": "ops-pass", "is_admin": False},
        ]
    }
    save_auth_resp = admin_client.put(
        "/api/admin/config-files/auth_users",
        json={"content": json.dumps(rewritten_auth, ensure_ascii=False, indent=2)},
    )
    assert save_auth_resp.status_code == 200
    save_auth_data = save_auth_resp.get_json()
    assert save_auth_data["content"]
    auth_file = Path(app.config["USERS_FILE"])
    persisted_auth = json.loads(auth_file.read_text(encoding="utf-8"))
    assert any(item["username"] == "ops" for item in persisted_auth["users"])

    env_config_resp = admin_client.get("/api/admin/config-files/app_env")
    assert env_config_resp.status_code == 200
    env_config_data = env_config_resp.get_json()
    assert env_config_data["requires_restart"] is True
    assert "AI_BASE_URL=https://example.invalid/v1" in env_config_data["content"]

    save_env_resp = admin_client.put(
        "/api/admin/config-files/app_env",
        json={
            "content": (
                "AI_BASE_URL=https://new.example/v1\n"
                "AI_API_KEY=new-key\n"
                "AI_MODELS=gpt-4o-mini,gpt-4.1-mini\n"
                "MAX_UPLOAD_MB=8\n"
                "MAX_ATTACHMENTS_PER_MESSAGE=3\n"
                "MAX_TEXT_FILE_CHARS=4096\n"
                "ALLOWED_ATTACHMENT_EXTS=.png,.docx\n"
                "LOG_LEVEL=INFO\n"
            )
        },
    )
    assert save_env_resp.status_code == 200
    save_env_data = save_env_resp.get_json()
    hot_reload = save_env_data["hot_reload"]
    assert set(hot_reload["applied_keys"]) == {
        "AI_API_KEY",
        "AI_BASE_URL",
        "AI_MODELS",
        "ALLOWED_ATTACHMENT_EXTS",
        "MAX_ATTACHMENTS_PER_MESSAGE",
        "MAX_TEXT_FILE_CHARS",
        "MAX_UPLOAD_MB",
    }
    assert hot_reload["restart_required_keys"] == ["LOG_LEVEL"]

    env_file = Path(app.config["ENV_FILE"])
    env_text = env_file.read_text(encoding="utf-8")
    assert "AI_BASE_URL=https://new.example/v1" in env_text
    assert "LOG_LEVEL=INFO" in env_text

    runtime_settings = app.extensions["runtime_state"].settings
    assert runtime_settings.ai_base_url == "https://new.example/v1"
    assert runtime_settings.ai_api_key == "new-key"
    assert runtime_settings.models == ["gpt-4o-mini", "gpt-4.1-mini"]
    assert runtime_settings.max_upload_mb == 8
    assert runtime_settings.max_upload_bytes == 8 * 1024 * 1024
    assert runtime_settings.max_attachments_per_message == 3
    assert runtime_settings.max_text_file_chars == 4096
    assert runtime_settings.allowed_attachment_exts == {".docx", ".png"}

    create_conv_resp = admin_client.post("/api/conversations", json={"model": "gpt-4.1-mini"})
    assert create_conv_resp.status_code == 201

    chat_page_resp = admin_client.get("/chat")
    assert chat_page_resp.status_code == 200
    chat_page_text = chat_page_resp.get_data(as_text=True)
    assert "gpt-4.1-mini" in chat_page_text
    assert "maxAttachmentsPerMessage: 3" in chat_page_text
    assert "maxUploadMB: 8" in chat_page_text
    assert ".docx" in chat_page_text
    assert ".png" in chat_page_text
