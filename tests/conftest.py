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


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    users_file = tmp_path / "users.json"
    users_file.write_text('{"users":{"u":"p"}}', encoding="utf-8")

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
def client(app):
    return app.test_client()


@pytest.fixture()
def logged_in_client(client):
    resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert resp.status_code == 200
    return client
