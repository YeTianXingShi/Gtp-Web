from __future__ import annotations


def test_bootstrap_requires_login(client):
    resp = client.get("/api/bootstrap")
    assert resp.status_code == 401


def test_bootstrap_returns_user_models_attachments(logged_in_client):
    resp = logged_in_client.get("/api/bootstrap")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True

    assert data["user"]["username"] == "u"
    assert data["user"]["is_admin"] is False

    # models.options 应包含至少 1 个模型
    options = data["models"]["options"]
    assert isinstance(options, list) and options
    first = options[0]
    assert "id" in first and "label" in first and "provider" in first

    # models.groups 按 provider 分组
    groups = data["models"]["groups"]
    assert isinstance(groups, list) and groups
    assert all("key" in g and "label" in g and "options" in g for g in groups)

    # 附件限制
    assert data["attachments"]["max_per_message"] >= 1
    assert data["attachments"]["max_upload_mb"] >= 1
    assert isinstance(data["attachments"]["allowed_exts"], list)


def test_tutorial_requires_login(client):
    resp = client.get("/api/tutorial")
    assert resp.status_code == 401


def test_tutorial_returns_markdown(logged_in_client):
    resp = logged_in_client.get("/api/tutorial")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "content" in data
    assert "exists" in data


def test_clients_config_requires_login(client):
    resp = client.get("/api/clients-config")
    assert resp.status_code == 401


def test_clients_config_returns_base_urls_and_empty_keys(logged_in_client):
    resp = logged_in_client.get("/api/clients-config")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["openai"]["base_url"] == "https://example.invalid/v1"
    # 默认测试用户没有自定义 api_keys，应返回空串
    assert data["openai"]["api_key"] == ""
    assert data["claude"]["base_url"] == ""
    assert data["claude"]["api_key"] == ""
