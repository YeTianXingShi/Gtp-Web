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
        "env_openai",
        "env_google",
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

    app_config_resp = admin_client.get("/api/admin/config-files/env_app")
    assert app_config_resp.status_code == 200
    app_config_data = app_config_resp.get_json()
    assert "IMAGE_TOOL_PROVIDER=openai" in app_config_data["content"]

    save_app_resp = admin_client.put(
        "/api/admin/config-files/env_app",
        json={
            "content": (
                "APP_SECRET_KEY=test-secret\n"
                "PORT=8000\n"
                "FLASK_DEBUG=1\n"
                "IMAGE_TOOL_PROVIDER=google\n"
            )
        },
    )
    assert save_app_resp.status_code == 200
    save_app_data = save_app_resp.get_json()
    assert save_app_data["hot_reload"]["applied_keys"] == ["IMAGE_TOOL_PROVIDER"]
    assert save_app_data["hot_reload"]["restart_required_keys"] == []

    openai_config_resp = admin_client.get("/api/admin/config-files/env_openai")
    assert openai_config_resp.status_code == 200
    openai_config_data = openai_config_resp.get_json()
    assert openai_config_data["requires_restart"] is True
    assert "OPENAI_BASE_URL=https://example.invalid/v1" in openai_config_data["content"]

    save_openai_resp = admin_client.put(
        "/api/admin/config-files/env_openai",
        json={
            "content": (
                "OPENAI_BASE_URL=https://new.example/v1\n"
                "OPENAI_API_KEY=new-key\n"
                "OPENAI_MODELS=gpt-4o-mini,gpt-4.1-mini\n"
                "OPENAI_IMAGE_MODEL=gpt-image-1\n"
            )
        },
    )
    assert save_openai_resp.status_code == 200
    save_openai_data = save_openai_resp.get_json()
    assert set(save_openai_data["hot_reload"]["applied_keys"]) == {
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODELS",
        "OPENAI_IMAGE_MODEL",
    }
    assert save_openai_data["hot_reload"]["restart_required_keys"] == []

    google_config_resp = admin_client.get("/api/admin/config-files/env_google")
    assert google_config_resp.status_code == 200
    google_config_data = google_config_resp.get_json()
    assert google_config_data["requires_restart"] is True

    save_google_resp = admin_client.put(
        "/api/admin/config-files/env_google",
        json={
            "content": (
                "GOOGLE_BASE_URL=https://gemini-proxy.example\n"
                "GOOGLE_API_KEY=google-new-key\n"
                "GOOGLE_MODELS=gemini-2.0-flash\n"
                "GOOGLE_IMAGE_MODEL=imagen-3.0-generate-002\n"
            )
        },
    )
    assert save_google_resp.status_code == 200
    save_google_data = save_google_resp.get_json()
    assert set(save_google_data["hot_reload"]["applied_keys"]) == {
        "GOOGLE_BASE_URL",
        "GOOGLE_API_KEY",
        "GOOGLE_MODELS",
        "GOOGLE_IMAGE_MODEL",
    }
    assert save_google_data["hot_reload"]["restart_required_keys"] == []

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
    app_env_text = Path(env_files[0]).read_text(encoding="utf-8")
    openai_env_text = Path(env_files[1]).read_text(encoding="utf-8")
    google_env_text = Path(env_files[2]).read_text(encoding="utf-8")
    attachments_env_text = Path(env_files[4]).read_text(encoding="utf-8")
    logging_env_text = Path(env_files[5]).read_text(encoding="utf-8")
    assert "IMAGE_TOOL_PROVIDER=google" in app_env_text
    assert "OPENAI_BASE_URL=https://new.example/v1" in openai_env_text
    assert "OPENAI_IMAGE_MODEL=gpt-image-1" in openai_env_text
    assert "GOOGLE_BASE_URL=https://gemini-proxy.example" in google_env_text
    assert "GOOGLE_IMAGE_MODEL=imagen-3.0-generate-002" in google_env_text
    assert "MAX_UPLOAD_MB=8" in attachments_env_text
    assert "LOG_LEVEL=INFO" in logging_env_text

    runtime_settings = app.extensions["runtime_state"].settings
    assert runtime_settings.image_tool_provider == "google"
    assert runtime_settings.openai_base_url == "https://new.example/v1"
    assert runtime_settings.openai_api_key == "new-key"
    assert runtime_settings.openai_models == ["gpt-4o-mini", "gpt-4.1-mini"]
    assert runtime_settings.openai_image_model == "gpt-image-1"
    assert runtime_settings.google_base_url == "https://gemini-proxy.example"
    assert runtime_settings.google_api_key == "google-new-key"
    assert runtime_settings.google_models == ["gemini-2.0-flash"]
    assert runtime_settings.google_image_model == "imagen-3.0-generate-002"
    assert runtime_settings.models == [
        "openai:gpt-4o-mini",
        "openai:gpt-4.1-mini",
        "google:gemini-2.0-flash",
    ]
    assert runtime_settings.max_upload_mb == 8
    assert runtime_settings.max_upload_bytes == 8 * 1024 * 1024
    assert runtime_settings.max_attachments_per_message == 3
    assert runtime_settings.max_text_file_chars == 4096
    assert runtime_settings.allowed_attachment_exts == {".docx", ".png"}

    create_conv_resp = admin_client.post("/api/conversations", json={"model": "openai:gpt-4.1-mini"})
    assert create_conv_resp.status_code == 201

    chat_page_resp = admin_client.get("/chat")
    assert chat_page_resp.status_code == 200
    chat_page_text = chat_page_resp.get_data(as_text=True)
    assert "gpt-4.1-mini" in chat_page_text
    assert "gemini-2.0-flash" in chat_page_text
    assert "maxAttachmentsPerMessage: 3" in chat_page_text
    assert "maxUploadMB: 8" in chat_page_text
    assert ".docx" in chat_page_text
    assert ".png" in chat_page_text
