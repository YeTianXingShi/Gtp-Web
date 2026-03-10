from __future__ import annotations

from pathlib import Path

import pytest


class _FakeStream:
    def __iter__(self):
        yield {"choices": [{"delta": {"content": "ok"}}]}


class _FakeCompletions:
    def __init__(self, seen_requests: list[dict]):
        self._seen_requests = seen_requests

    def create(self, **kwargs):
        self._seen_requests.append(kwargs)
        return _FakeStream()


class _FakeChat:
    def __init__(self, seen_requests: list[dict]):
        self.completions = _FakeCompletions(seen_requests)


class _FakeOpenAI:
    def __init__(self, seen_requests: list[dict], **_kwargs):
        self.chat = _FakeChat(seen_requests)


def _create_test_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    users_file = tmp_path / "users.json"
    users_file.write_text(
        '{"users":[{"username":"admin","password":"admin-pass","is_admin":true},{"username":"u","password":"p","is_admin":false}]}',
        encoding="utf-8",
    )

    monkeypatch.delenv("ENV_DIR", raising=False)
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "app.env").write_text(
        "APP_SECRET_KEY=test-secret\nPORT=8000\nFLASK_DEBUG=1\n",
        encoding="utf-8",
    )
    (env_dir / "ai.env").write_text(
        "AI_BASE_URL=https://example.invalid/v1\nAI_API_KEY=test-key\nAI_MODELS=gpt-4o-mini\n",
        encoding="utf-8",
    )
    (env_dir / "storage.env").write_text(
        "CHAT_DB_FILE=./data/chat.db\nUPLOAD_DIR=./data/uploads\n",
        encoding="utf-8",
    )
    (env_dir / "attachments.env").write_text(
        "MAX_UPLOAD_MB=15\nMAX_ATTACHMENTS_PER_MESSAGE=5\nMAX_TEXT_FILE_CHARS=12000\nALLOWED_ATTACHMENT_EXTS=.txt,.md,.json,.csv,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx\n",
        encoding="utf-8",
    )
    (env_dir / "logging.env").write_text(
        "LOG_LEVEL=DEBUG\nLOG_FILE=./logs/app.log\nLOG_MAX_BYTES=10485760\nLOG_BACKUP_COUNT=5\nLOG_TO_STDOUT=1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_DIR", str(env_dir))

    monkeypatch.setenv("USERS_FILE", str(users_file))
    monkeypatch.setenv("CHAT_DB_FILE", str(tmp_path / "chat.db"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("AI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODELS", "gpt-4o-mini")
    monkeypatch.setenv(
        "ALLOWED_ATTACHMENT_EXTS",
        ".txt,.md,.json,.csv,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx",
    )

    from gtpweb import app_factory

    seen_requests: list[dict] = []

    def _build_fake_openai(**kwargs):
        return _FakeOpenAI(seen_requests=seen_requests, **kwargs)

    monkeypatch.setattr(app_factory, "OpenAI", _build_fake_openai)

    flask_app = app_factory.create_app()
    flask_app.config.update(TESTING=True)
    flask_app.extensions["seen_openai_requests"] = seen_requests
    return flask_app


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    return _create_test_app(monkeypatch, tmp_path)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def logged_in_client(client):
    resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert resp.status_code == 200
    return client


@pytest.fixture()
def admin_client(client):
    resp = client.post("/api/login", json={"username": "admin", "password": "admin-pass"})
    assert resp.status_code == 200
    return client
