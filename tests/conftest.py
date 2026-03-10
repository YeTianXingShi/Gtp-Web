from __future__ import annotations

import base64
from pathlib import Path

import pytest

PNG_1X1_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?"
    b"\x00\x05\xfe\x02\xfeA\x0f\x95~\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


class _FakeImageItem:
    def __init__(self, image_bytes: bytes):
        self.b64_json = base64.b64encode(image_bytes).decode("ascii")


class _FakeImageResponse:
    def __init__(self, image_bytes: bytes):
        self.data = [_FakeImageItem(image_bytes)]


class _FakeImages:
    def __init__(self, seen_requests: list[dict], image_bytes: bytes):
        self._seen_requests = seen_requests
        self._image_bytes = image_bytes

    def generate(self, **kwargs):
        self._seen_requests.append(kwargs)
        return _FakeImageResponse(self._image_bytes)


class _FakeOpenAI:
    def __init__(
        self,
        seen_requests: list[dict],
        seen_image_requests: list[dict],
        stream_text: str,
        image_bytes: bytes,
        **_kwargs,
    ):
        self.chat = _FakeChat(seen_requests, stream_text)
        self.images = _FakeImages(seen_image_requests, image_bytes)


class _FakeGoogleChunk:
    def __init__(self, text: str):
        self.text = text


class _FakeGoogleImage:
    def __init__(self, image_bytes: bytes, mime_type: str = "image/png"):
        self.image_bytes = image_bytes
        self.mime_type = mime_type


class _FakeGeneratedImage:
    def __init__(self, image_bytes: bytes, mime_type: str = "image/png"):
        self.image = _FakeGoogleImage(image_bytes=image_bytes, mime_type=mime_type)
        self.rai_filtered_reason = None


class _FakeGenerateImagesResponse:
    def __init__(self, image_bytes: bytes):
        self.generated_images = [_FakeGeneratedImage(image_bytes=image_bytes)]


class _FakeGoogleBlob:
    def __init__(self, image_bytes: bytes, mime_type: str = "image/png"):
        self.data = image_bytes
        self.mime_type = mime_type


class _FakeGooglePart:
    def __init__(self, image_bytes: bytes, mime_type: str = "image/png"):
        self.inline_data = _FakeGoogleBlob(image_bytes=image_bytes, mime_type=mime_type)
        self.text = None


class _FakeGenerateContentImageResponse:
    def __init__(self, image_bytes: bytes):
        self.parts = [_FakeGooglePart(image_bytes=image_bytes)]


class _FakeGoogleModels:
    def __init__(
        self,
        seen_requests: list[dict],
        seen_generate_images_requests: list[dict],
        seen_generate_content_image_requests: list[dict],
        stream_text: str,
        image_bytes: bytes,
    ):
        self._seen_requests = seen_requests
        self._seen_generate_images_requests = seen_generate_images_requests
        self._seen_generate_content_image_requests = seen_generate_content_image_requests
        self._stream_text = stream_text
        self._image_bytes = image_bytes

    def generate_content_stream(self, **kwargs):
        self._seen_requests.append(kwargs)
        return [_FakeGoogleChunk(self._stream_text)]

    def generate_images(self, **kwargs):
        self._seen_generate_images_requests.append(kwargs)
        return _FakeGenerateImagesResponse(self._image_bytes)

    def generate_content(self, **kwargs):
        self._seen_generate_content_image_requests.append(kwargs)
        return _FakeGenerateContentImageResponse(self._image_bytes)


class _FakeGoogleClient:
    def __init__(
        self,
        seen_requests: list[dict],
        seen_generate_images_requests: list[dict],
        seen_generate_content_image_requests: list[dict],
        stream_text: str,
        image_bytes: bytes,
        **_kwargs,
    ):
        self.models = _FakeGoogleModels(
            seen_requests=seen_requests,
            seen_generate_images_requests=seen_generate_images_requests,
            seen_generate_content_image_requests=seen_generate_content_image_requests,
            stream_text=stream_text,
            image_bytes=image_bytes,
        )



def _create_test_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    app_env_text: str | None = None,
    openai_env_text: str | None = None,
    google_env_text: str | None = None,
    openai_stream_text: str = "ok",
    google_stream_text: str = "ok",
    image_bytes: bytes = PNG_1X1_BYTES,
):
    users_file = tmp_path / "users.json"
    users_file.write_text(
        '{"users":[{"username":"admin","password":"admin-pass","is_admin":true},{"username":"u","password":"p","is_admin":false}]}',
        encoding="utf-8",
    )

    for key in (
        "ENV_DIR",
        "IMAGE_TOOL_PROVIDER",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_MODELS",
        "OPENAI_IMAGE_MODEL",
        "GOOGLE_BASE_URL",
        "GOOGLE_API_KEY",
        "GOOGLE_MODELS",
        "GOOGLE_IMAGE_MODEL",
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
            "IMAGE_TOOL_PROVIDER=openai\n"
        ),
        encoding="utf-8",
    )
    (env_dir / "openai.env").write_text(
        openai_env_text
        or (
            "OPENAI_BASE_URL=https://example.invalid/v1\n"
            "OPENAI_API_KEY=test-key\n"
            "OPENAI_MODELS=gpt-4o-mini\n"
            "OPENAI_IMAGE_MODEL=dall-e-3\n"
        ),
        encoding="utf-8",
    )
    (env_dir / "google.env").write_text(
        google_env_text
        or (
            "GOOGLE_BASE_URL=\n"
            "GOOGLE_API_KEY=\n"
            "GOOGLE_MODELS=\n"
            "GOOGLE_IMAGE_MODEL=\n"
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

    monkeypatch.setenv("USERS_FILE", str(users_file))
    monkeypatch.setenv("CHAT_DB_FILE", str(tmp_path / "chat.db"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv(
        "ALLOWED_ATTACHMENT_EXTS",
        ".txt,.md,.json,.csv,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx",
    )

    from gtpweb import app_factory

    seen_openai_requests: list[dict] = []
    seen_openai_image_requests: list[dict] = []
    seen_google_requests: list[dict] = []
    seen_google_image_requests: list[dict] = []
    seen_google_content_image_requests: list[dict] = []
    seen_google_client_kwargs: list[dict] = []

    def _build_fake_openai(**kwargs):
        return _FakeOpenAI(
            seen_requests=seen_openai_requests,
            seen_image_requests=seen_openai_image_requests,
            stream_text=openai_stream_text,
            image_bytes=image_bytes,
            **kwargs,
        )

    def _build_fake_google(**kwargs):
        seen_google_client_kwargs.append(dict(kwargs))
        return _FakeGoogleClient(
            seen_requests=seen_google_requests,
            seen_generate_images_requests=seen_google_image_requests,
            seen_generate_content_image_requests=seen_google_content_image_requests,
            stream_text=google_stream_text,
            image_bytes=image_bytes,
            **kwargs,
        )

    monkeypatch.setattr(app_factory, "build_openai_client", _build_fake_openai)
    monkeypatch.setattr(app_factory, "build_google_client", _build_fake_google)

    flask_app = app_factory.create_app()
    flask_app.config.update(TESTING=True)
    flask_app.extensions["seen_openai_requests"] = seen_openai_requests
    flask_app.extensions["seen_openai_image_requests"] = seen_openai_image_requests
    flask_app.extensions["seen_google_requests"] = seen_google_requests
    flask_app.extensions["seen_google_image_requests"] = seen_google_image_requests
    flask_app.extensions["seen_google_content_image_requests"] = seen_google_content_image_requests
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
