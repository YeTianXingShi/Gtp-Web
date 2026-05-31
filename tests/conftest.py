from __future__ import annotations

from pathlib import Path

import pytest


class _FakeStream:
    def __init__(self, text: str):
        self._text = text

    def __iter__(self):
        yield {"choices": [{"delta": {"content": self._text}}]}


class _FakeCompletions:
    def __init__(self, seen_requests: list[dict], stream_text: str):
        self._seen_requests = seen_requests
        self._stream_text = stream_text

    def create(self, **kwargs):
        self._seen_requests.append(kwargs)
        return _FakeStream(self._stream_text)


class _FakeChat:
    def __init__(self, seen_requests: list[dict], stream_text: str):
        self.completions = _FakeCompletions(seen_requests, stream_text)


class _FakeResponsesStream:
    def __init__(self, events: list[object]):
        self._events = list(events)

    def __iter__(self):
        yield from self._events


class _FakeResponses:
    def __init__(self, seen_requests: list[dict], response_events: list[object]):
        self._seen_requests = seen_requests
        self._response_events = list(response_events)

    def create(self, **kwargs):
        self._seen_requests.append(kwargs)
        return _FakeResponsesStream(self._response_events)


class _FakeFileObject:
    def __init__(self, file_id: str):
        self.id = file_id


class _FakeFiles:
    def __init__(self):
        self._counter = 0

    def create(self, **_kwargs):
        self._counter += 1
        return _FakeFileObject(f"file-fake-{self._counter}")


class _FakeOpenAI:
    def __init__(
        self,
        seen_requests: list[dict],
        stream_text: str,
        response_events: list[object] | None = None,
        **_kwargs,
    ):
        self.chat = _FakeChat(seen_requests, stream_text)
        self.responses = _FakeResponses(
            seen_requests,
            response_events
            or [{"type": "response.output_text.delta", "delta": stream_text}],
        )
        self.files = _FakeFiles()


class _FakeGoogleChunk:
    def __init__(self, text: str):
        self.text = text


class _FakeGoogleModels:
    def __init__(
        self,
        seen_requests: list[dict],
        stream_text: str,
    ):
        self._seen_requests = seen_requests
        self._stream_text = stream_text

    def generate_content_stream(self, **kwargs):
        self._seen_requests.append(kwargs)
        return [_FakeGoogleChunk(self._stream_text)]

    def generate_content(self, **kwargs):
        return _FakeGoogleChunk(self._stream_text)


class _FakeGoogleClient:
    def __init__(
        self,
        seen_requests: list[dict],
        stream_text: str,
        **_kwargs,
    ):
        self.models = _FakeGoogleModels(
            seen_requests=seen_requests,
            stream_text=stream_text,
        )



def _create_test_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    app_env_text: str | None = None,
    openai_env_text: str | None = None,
    google_env_text: str | None = None,
    models_config_text: str | None = None,
    openai_stream_text: str = "ok",
    openai_response_events: list[object] | None = None,
    google_stream_text: str = "ok",
):
    users_file = tmp_path / "users.json"
    users_file.write_text(
        '{"users":[{"username":"admin","password":"admin-pass","is_admin":true},{"username":"u","password":"p","is_admin":false}]}',
        encoding="utf-8",
    )

    for key in (
        "ENV_DIR",
        "MODEL_CONFIG_FILE",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "GOOGLE_BASE_URL",
        "GOOGLE_API_KEY",
        "CLAUDE_BASE_URL",
        "CLAUDE_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "app.env").write_text(
        app_env_text
        or (
            "APP_SECRET_KEY=test-secret\n"
            "PORT=8000\n"
            "FLASK_DEBUG=1\n"
        ),
        encoding="utf-8",
    )
    (env_dir / "openai.env").write_text(
        openai_env_text
        or (
            "OPENAI_BASE_URL=https://example.invalid/v1\n"
            "OPENAI_API_KEY=test-key\n"
        ),
        encoding="utf-8",
    )
    (env_dir / "google.env").write_text(
        google_env_text
        or (
            "GOOGLE_BASE_URL=\n"
            "GOOGLE_API_KEY=\n"
        ),
        encoding="utf-8",
    )
    (env_dir / "claude.env").write_text(
        "CLAUDE_BASE_URL=\n"
        "CLAUDE_API_KEY=\n",
        encoding="utf-8",
    )
    models_file = tmp_path / "models.jsonc"
    models_file.write_text(
        models_config_text
        or (
            '{\n'
            '  "openai": {\n'
            '    "models": [\n'
            '      {"name": "gpt-4o-mini"}\n'
            '    ]\n'
            '  },\n'
            '  "google": {\n'
            '    "models": []\n'
            '  },\n'
            '  "claude": {\n'
            '    "models": []\n'
            '  }\n'
            '}\n'
        ),
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
    monkeypatch.setenv("MODEL_CONFIG_FILE", str(models_file))

    monkeypatch.setenv("USERS_FILE", str(users_file))
    monkeypatch.setenv("CHAT_DB_FILE", str(tmp_path / "chat.db"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv(
        "ALLOWED_ATTACHMENT_EXTS",
        ".txt,.md,.json,.csv,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx",
    )

    from gtpweb import app_factory

    seen_openai_requests: list[dict] = []
    seen_google_requests: list[dict] = []
    seen_google_client_kwargs: list[dict] = []

    def _build_fake_openai(**kwargs):
        return _FakeOpenAI(
            seen_requests=seen_openai_requests,
            stream_text=openai_stream_text,
            response_events=openai_response_events,
            **kwargs,
        )

    def _build_fake_google(**kwargs):
        seen_google_client_kwargs.append(dict(kwargs))
        return _FakeGoogleClient(
            seen_requests=seen_google_requests,
            stream_text=google_stream_text,
            **kwargs,
        )

    def _build_fake_claude(**kwargs):
        return None

    monkeypatch.setattr(app_factory, "build_openai_client", _build_fake_openai)
    monkeypatch.setattr(app_factory, "build_google_client", _build_fake_google)
    monkeypatch.setattr(app_factory, "build_claude_client", _build_fake_claude)

    flask_app = app_factory.create_app()
    flask_app.config.update(TESTING=True)
    flask_app.extensions["seen_openai_requests"] = seen_openai_requests
    flask_app.extensions["seen_google_requests"] = seen_google_requests
    flask_app.extensions["seen_google_client_kwargs"] = seen_google_client_kwargs
    return flask_app


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    return _create_test_app(monkeypatch, tmp_path)


@pytest.fixture()
def app_builder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def _build(**kwargs):
        return _create_test_app(monkeypatch, tmp_path, **kwargs)

    return _build


@pytest.fixture()
def client(app):
    return app.test_client()


class _AuthedClient:
    """对 Flask test_client 的轻量包装：自动注入 Authorization 头。

    使用方式与 test_client 一致：authed.get("/api/...")，无需手动设置 header。
    自身也提供 .access_token / .user 属性方便测试断言。
    """

    def __init__(self, client, access_token: str, user: dict):
        self._client = client
        self.access_token = access_token
        self.user = user

    def _inject(self, kwargs: dict) -> dict:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Authorization", f"Bearer {self.access_token}")
        kwargs["headers"] = headers
        return kwargs

    def get(self, *args, **kwargs):
        return self._client.get(*args, **self._inject(kwargs))

    def post(self, *args, **kwargs):
        return self._client.post(*args, **self._inject(kwargs))

    def put(self, *args, **kwargs):
        return self._client.put(*args, **self._inject(kwargs))

    def patch(self, *args, **kwargs):
        return self._client.patch(*args, **self._inject(kwargs))

    def delete(self, *args, **kwargs):
        return self._client.delete(*args, **self._inject(kwargs))

    def open(self, *args, **kwargs):
        return self._client.open(*args, **self._inject(kwargs))

    def __getattr__(self, name):
        # 回退到底层 client 的其他属性（如 cookie_jar、application 等）
        return getattr(self._client, name)


def _login_authed(client, *, username: str, password: str) -> _AuthedClient:
    resp = client.post("/api/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data["ok"] is True, data
    return _AuthedClient(client, access_token=data["access_token"], user=data["user"])


@pytest.fixture()
def logged_in_client(client) -> _AuthedClient:
    return _login_authed(client, username="u", password="p")


@pytest.fixture()
def admin_client(client) -> _AuthedClient:
    return _login_authed(client, username="admin", password="admin-pass")
