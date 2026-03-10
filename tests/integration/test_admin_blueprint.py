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


def test_admin_can_edit_grouped_config_files_and_hot_reload(admin_client, app):
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
    assert file_ids == [
        "auth_users",
        "env_app",
        "env_ai",
        "env_storage",
        "env_attachments",
        "env_logging",
    ]

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

    ai_config_resp = admin_client.get("/api/admin/config-files/env_ai")
    assert ai_config_resp.status_code == 200
    ai_config_data = ai_config_resp.get_json()
    assert ai_config_data["requires_restart"] is True
    assert "AI_BASE_URL=https://example.invalid/v1" in ai_config_data["content"]

    save_ai_resp = admin_client.put(
        "/api/admin/config-files/env_ai",
        json={
            "content": (
                "AI_BASE_URL=https://new.example/v1\n"
                "AI_API_KEY=new-key\n"
                "AI_MODELS=gpt-4o-mini,gpt-4.1-mini\n"
            )
        },
    )
    assert save_ai_resp.status_code == 200
    save_ai_data = save_ai_resp.get_json()
    assert set(save_ai_data["hot_reload"]["applied_keys"]) == {
        "AI_API_KEY",
        "AI_BASE_URL",
        "AI_MODELS",
    }
    assert save_ai_data["hot_reload"]["restart_required_keys"] == []

    save_attachment_resp = admin_client.put(
        "/api/admin/config-files/env_attachments",
        json={
            "content": (
                "MAX_UPLOAD_MB=8\n"
                "MAX_ATTACHMENTS_PER_MESSAGE=3\n"
                "MAX_TEXT_FILE_CHARS=4096\n"
                "ALLOWED_ATTACHMENT_EXTS=.png,.docx\n"
            )
        },
    )
    assert save_attachment_resp.status_code == 200
    save_attachment_data = save_attachment_resp.get_json()
    assert set(save_attachment_data["hot_reload"]["applied_keys"]) == {
        "ALLOWED_ATTACHMENT_EXTS",
        "MAX_ATTACHMENTS_PER_MESSAGE",
        "MAX_TEXT_FILE_CHARS",
        "MAX_UPLOAD_MB",
    }
    assert save_attachment_data["hot_reload"]["restart_required_keys"] == []

    save_logging_resp = admin_client.put(
        "/api/admin/config-files/env_logging",
        json={
            "content": (
                "LOG_LEVEL=INFO\n"
                "LOG_FILE=./logs/app.log\n"
                "LOG_MAX_BYTES=10485760\n"
                "LOG_BACKUP_COUNT=5\n"
                "LOG_TO_STDOUT=1\n"
            )
        },
    )
    assert save_logging_resp.status_code == 200
    save_logging_data = save_logging_resp.get_json()
    assert save_logging_data["hot_reload"]["applied_keys"] == []
    assert save_logging_data["hot_reload"]["restart_required_keys"] == ["LOG_LEVEL"]

    env_files = app.config["ENV_FILES"]
    ai_env_text = Path(env_files[1]).read_text(encoding="utf-8")
    attachments_env_text = Path(env_files[3]).read_text(encoding="utf-8")
    logging_env_text = Path(env_files[4]).read_text(encoding="utf-8")
    assert "AI_BASE_URL=https://new.example/v1" in ai_env_text
    assert "MAX_UPLOAD_MB=8" in attachments_env_text
    assert "LOG_LEVEL=INFO" in logging_env_text

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
