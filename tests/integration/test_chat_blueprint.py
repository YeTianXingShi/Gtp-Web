from __future__ import annotations

import io

from docx import Document

PNG_1X1_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?"
    b"\x00\x05\xfe\x02\xfeA\x0f\x95~\x00\x00\x00\x00IEND\xaeB`\x82"
)



class _OpenAITextStream:
    def __init__(self, *chunks: str):
        self._chunks = list(chunks)

    def __iter__(self):
        for chunk in self._chunks:
            yield {"choices": [{"delta": {"content": chunk}}]}


class _OpenAITextStreamWithError:
    def __init__(self, chunks: list[str], error_message: str):
        self._chunks = list(chunks)
        self._error_message = error_message

    def __iter__(self):
        for chunk in self._chunks:
            yield {"choices": [{"delta": {"content": chunk}}]}
        raise RuntimeError(self._error_message)


def _install_openai_streams(app, streams: list[object]) -> None:
    runtime_state = app.extensions["runtime_state"]
    seen_requests = app.extensions["seen_openai_requests"]
    queue = list(streams)

    def _create(**kwargs):
        seen_requests.append(kwargs)
        if not queue:
            raise AssertionError("未配置足够的 OpenAI 流返回")
        return queue.pop(0)

    runtime_state.openai_client.chat.completions.create = _create


def _create_conversation(client) -> int:
    resp = client.post("/api/conversations", json={"model": "openai:gpt-4o-mini"})
    assert resp.status_code == 201
    return int(resp.get_json()["conversation"]["id"])



def test_chat_stream_with_text_attachment(logged_in_client, app):
    conv_id = _create_conversation(logged_in_client)

    resp = logged_in_client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "openai:gpt-4o-mini",
            "content": "请看附件",
            "files": [(io.BytesIO(b"hello"), "note.txt")],
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert '"type": "delta"' in body
    assert '"type": "done"' in body

    seen = app.extensions["seen_openai_requests"]
    assert seen



def test_chat_stream_rejects_non_whitelist_extension(logged_in_client):
    conv_id = _create_conversation(logged_in_client)

    resp = logged_in_client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "openai:gpt-4o-mini",
            "content": "bad file",
            "files": [(io.BytesIO(b"%PDF-1.4"), "forbidden.pdf")],
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "不支持的文件类型" in data["error"]



def test_chat_stream_accepts_unicode_docx_filename(logged_in_client):
    conv_id = _create_conversation(logged_in_client)

    doc = Document()
    doc.add_paragraph("测试中文文件名")
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    resp = logged_in_client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "openai:gpt-4o-mini",
            "content": "解析这个文档",
            "files": [(buffer, "📊 平台奖励政策与结算执行总表.docx")],
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    _ = resp.get_data(as_text=True)



def test_message_image_preview_url_and_order(logged_in_client):
    conv_id = _create_conversation(logged_in_client)

    resp = logged_in_client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "openai:gpt-4o-mini",
            "content": "按顺序看图",
            "files": [
                (io.BytesIO(PNG_1X1_BYTES), "first.png"),
                (io.BytesIO(PNG_1X1_BYTES), "second.png"),
            ],
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    _ = resp.get_data(as_text=True)

    list_resp = logged_in_client.get(f"/api/conversations/{conv_id}/messages")
    assert list_resp.status_code == 200
    data = list_resp.get_json()
    user_message = next(msg for msg in data["messages"] if msg["role"] == "user")
    attachments = user_message["attachments"]

    assert [att["file_name"] for att in attachments] == ["first.png", "second.png"]
    assert all(att["is_image"] for att in attachments)
    assert all(att["preview_url"] for att in attachments)

    preview_resp = logged_in_client.get(attachments[0]["preview_url"])
    assert preview_resp.status_code == 200
    assert preview_resp.mimetype.startswith("image/")


def test_unicode_image_attachment_preview_uses_safe_inline_disposition(logged_in_client):
    conv_id = _create_conversation(logged_in_client)

    resp = logged_in_client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "openai:gpt-4o-mini",
            "content": "看中文图片名",
            "files": [(io.BytesIO(PNG_1X1_BYTES), "中文预览图.png")],
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    _ = resp.get_data(as_text=True)

    list_resp = logged_in_client.get(f"/api/conversations/{conv_id}/messages")
    assert list_resp.status_code == 200
    data = list_resp.get_json()
    user_message = next(msg for msg in data["messages"] if msg["role"] == "user")
    attachment = user_message["attachments"][0]

    preview_resp = logged_in_client.get(attachment["preview_url"])
    assert preview_resp.status_code == 200
    disposition = preview_resp.headers["Content-Disposition"]
    disposition.encode("latin-1")
    assert disposition.startswith("inline;")
    assert "filename*=UTF-8''" in disposition
    assert ".png" in disposition



def test_google_chat_stream_uses_google_client_and_base_url(app_builder):
    app = app_builder(
        models_config_text=(
            '{\n'
            '  "openai": {"models": []},\n'
            '  "google": {"models": [{"name": "gemini-2.0-flash", "thinking": false}]}\n'
            '}\n'
        ),
        openai_env_text=(
            "OPENAI_BASE_URL=\n"
            "OPENAI_API_KEY=\n"
        ),
        google_env_text=(
            "GOOGLE_BASE_URL=https://gemini-proxy.example\n"
            "GOOGLE_API_KEY=google-test-key\n"
        ),
    )
    client = app.test_client()

    login_resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert login_resp.status_code == 200

    create_resp = client.post(
        "/api/conversations",
        json={"model": "google:gemini-2.0-flash"},
    )
    assert create_resp.status_code == 201
    conv_id = int(create_resp.get_json()["conversation"]["id"])

    resp = client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "google:gemini-2.0-flash",
            "content": "你好，Gemini",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert '"type": "delta"' in body
    assert '"type": "done"' in body

    seen_requests = app.extensions["seen_google_requests"]
    assert seen_requests
    assert seen_requests[0]["model"] == "gemini-2.0-flash"

    seen_client_kwargs = app.extensions["seen_google_client_kwargs"]
    assert seen_client_kwargs
    assert seen_client_kwargs[0]["api_key"] == "google-test-key"
    assert seen_client_kwargs[0]["base_url"] == "https://gemini-proxy.example"

def test_openai_reasoning_summary_is_persisted_in_messages(app_builder):
    app = app_builder(
        models_config_text=(
            '{\n'
            '  "openai": {\n'
            '    "models": [{"name": "gpt-5-mini", "reasoning": {"effort": "high", "summary": "auto"}}]\n'
            '  },\n'
            '  "google": {"models": []}\n'
            '}\n'
        ),
        openai_env_text=(
            "OPENAI_BASE_URL=https://example.invalid/v1\n"
            "OPENAI_API_KEY=test-key\n"
        ),
        openai_response_events=[
            {"type": "response.reasoning_summary_text.delta", "delta": "先整理已知条件。"},
            {"type": "response.reasoning_summary_text.delta", "delta": "再给出结论。"},
            {"type": "response.output_text.delta", "delta": "这是最终回复。"},
        ],
    )
    client = app.test_client()

    login_resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert login_resp.status_code == 200

    create_resp = client.post(
        "/api/conversations",
        json={"model": "openai:gpt-5-mini"},
    )
    assert create_resp.status_code == 201
    conv_id = int(create_resp.get_json()["conversation"]["id"])

    stream_resp = client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "openai:gpt-5-mini",
            "content": "请认真思考后回答",
        },
        content_type="multipart/form-data",
    )
    assert stream_resp.status_code == 200
    stream_body = stream_resp.get_data(as_text=True)
    assert '"type": "reasoning"' in stream_body
    assert '"type": "done"' in stream_body

    list_resp = client.get(f"/api/conversations/{conv_id}/messages")
    assert list_resp.status_code == 200
    messages = list_resp.get_json()["messages"]
    assistant_message = next(msg for msg in messages if msg["role"] == "assistant")

    assert assistant_message["content"] == "这是最终回复。"
    assert assistant_message["reasoning"] == "先整理已知条件。再给出结论。"
    seen_requests = app.extensions["seen_openai_requests"]
    assert seen_requests[0]["reasoning"] == {"effort": "high", "summary": "auto"}


def test_openai_reasoning_enabled_false_falls_back_to_chat_completions(app_builder):
    app = app_builder(
        models_config_text=(
            '{\n'
            '  "openai": {\n'
            '    "defaults": {"reasoning": {"enabled": true, "effort": "high", "summary": "auto"}},\n'
            '    "models": [{"name": "gpt-5-mini", "reasoning": {"enabled": false}}]\n'
            '  },\n'
            '  "google": {"models": []}\n'
            '}\n'
        ),
    )
    client = app.test_client()

    login_resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert login_resp.status_code == 200

    create_resp = client.post(
        "/api/conversations",
        json={"model": "openai:gpt-5-mini"},
    )
    assert create_resp.status_code == 201
    conv_id = int(create_resp.get_json()["conversation"]["id"])

    resp = client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "openai:gpt-5-mini",
            "content": "这次不要走 reasoning",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    _ = resp.get_data(as_text=True)

    seen_requests = app.extensions["seen_openai_requests"]
    assert seen_requests
    assert seen_requests[0].get("reasoning") is None
    assert "messages" in seen_requests[0]
    assert "input" not in seen_requests[0]


def test_google_model_specific_thinking_config_is_applied(app_builder):
    app = app_builder(
        models_config_text=(
            '{\n'
            '  "openai": {"models": []},\n'
            '  "google": {\n'
            '    "models": [{"name": "gemini-2.5-pro", "thinking": {"include_thoughts": true, "budget": 1024}}]\n'
            '  }\n'
            '}\n'
        ),
        openai_env_text=(
            "OPENAI_BASE_URL=\n"
            "OPENAI_API_KEY=\n"
        ),
        google_env_text=(
            "GOOGLE_BASE_URL=https://gemini-proxy.example\n"
            "GOOGLE_API_KEY=google-test-key\n"
        ),
    )
    client = app.test_client()

    login_resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert login_resp.status_code == 200

    create_resp = client.post(
        "/api/conversations",
        json={"model": "google:gemini-2.5-pro"},
    )
    assert create_resp.status_code == 201
    conv_id = int(create_resp.get_json()["conversation"]["id"])

    resp = client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "google:gemini-2.5-pro",
            "content": "请多思考一下",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    _ = resp.get_data(as_text=True)

    seen_requests = app.extensions["seen_google_requests"]
    assert seen_requests
    config = seen_requests[0]["config"]
    thinking_config = getattr(config, "thinking_config", None)
    assert thinking_config is not None
    assert getattr(thinking_config, "include_thoughts", None) is True
    assert getattr(thinking_config, "thinking_budget", None) == 1024


def test_google_thinking_can_hide_thoughts_without_disabling_thinking(app_builder):
    app = app_builder(
        models_config_text=(
            '{\n'
            '  "openai": {"models": []},\n'
            '  "google": {\n'
            '    "models": [{"name": "gemini-2.5-pro", "thinking": {"enabled": true, "include_thoughts": false, "level": "high"}}]\n'
            '  }\n'
            '}\n'
        ),
        openai_env_text=(
            "OPENAI_BASE_URL=\n"
            "OPENAI_API_KEY=\n"
        ),
        google_env_text=(
            "GOOGLE_BASE_URL=https://gemini-proxy.example\n"
            "GOOGLE_API_KEY=google-test-key\n"
        ),
    )
    client = app.test_client()

    login_resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert login_resp.status_code == 200

    create_resp = client.post(
        "/api/conversations",
        json={"model": "google:gemini-2.5-pro"},
    )
    assert create_resp.status_code == 201
    conv_id = int(create_resp.get_json()["conversation"]["id"])

    resp = client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "google:gemini-2.5-pro",
            "content": "请认真思考，但别回传 thoughts",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    _ = resp.get_data(as_text=True)

    seen_requests = app.extensions["seen_google_requests"]
    assert seen_requests
    config = seen_requests[0]["config"]
    thinking_config = getattr(config, "thinking_config", None)
    assert thinking_config is not None
    assert getattr(thinking_config, "include_thoughts", None) is False
    thinking_level = getattr(thinking_config, "thinking_level", None)
    assert str(getattr(thinking_level, "value", thinking_level)).lower() == "high"



def test_retry_chat_stream_reuses_last_user_message_after_empty_failure(app_builder):
    app = app_builder()
    client = app.test_client()

    login_resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert login_resp.status_code == 200

    conv_id = _create_conversation(client)
    _install_openai_streams(
        app,
        [
            _OpenAITextStreamWithError([], "上游临时不可用"),
            _OpenAITextStream("重试后拿到完整回复。"),
        ],
    )

    first_resp = client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "openai:gpt-4o-mini",
            "content": "第一次先失败",
        },
        content_type="multipart/form-data",
    )
    assert first_resp.status_code == 200
    first_body = first_resp.get_data(as_text=True)
    assert '"type": "error"' in first_body
    assert "上游临时不可用" in first_body

    messages_resp = client.get(f"/api/conversations/{conv_id}/messages")
    assert messages_resp.status_code == 200
    messages = messages_resp.get_json()["messages"]
    assert [msg["role"] for msg in messages] == ["user"]
    assert messages[0]["status"] == "complete"

    retry_resp = client.post(
        "/api/chat/retry/stream",
        data={"conversation_id": str(conv_id)},
        content_type="multipart/form-data",
    )
    assert retry_resp.status_code == 200
    retry_body = retry_resp.get_data(as_text=True)
    assert '"type": "delta"' in retry_body
    assert '"type": "done"' in retry_body
    assert "重试后拿到完整回复。" in retry_body

    final_messages_resp = client.get(f"/api/conversations/{conv_id}/messages")
    assert final_messages_resp.status_code == 200
    final_messages = final_messages_resp.get_json()["messages"]
    assert [msg["role"] for msg in final_messages] == ["user", "assistant"]
    assert final_messages[1]["content"] == "重试后拿到完整回复。"
    assert final_messages[1]["status"] == "complete"
    assert len(app.extensions["seen_openai_requests"]) == 2


def test_retry_chat_stream_replaces_incomplete_assistant_message(app_builder):
    app = app_builder()
    client = app.test_client()

    login_resp = client.post("/api/login", json={"username": "u", "password": "p"})
    assert login_resp.status_code == 200

    conv_id = _create_conversation(client)
    _install_openai_streams(
        app,
        [
            _OpenAITextStreamWithError(["先返回一半"], "上游临时不可用"),
            _OpenAITextStream("重试后的完整回复。"),
        ],
    )

    first_resp = client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "openai:gpt-4o-mini",
            "content": "给我一个会失败的回答",
        },
        content_type="multipart/form-data",
    )
    assert first_resp.status_code == 200
    first_body = first_resp.get_data(as_text=True)
    assert '"type": "error"' in first_body
    assert "先返回一半" in first_body

    messages_resp = client.get(f"/api/conversations/{conv_id}/messages")
    assert messages_resp.status_code == 200
    messages = messages_resp.get_json()["messages"]
    assert [msg["role"] for msg in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "先返回一半"
    assert messages[1]["status"] == "incomplete"

    retry_resp = client.post(
        "/api/chat/retry/stream",
        data={"conversation_id": str(conv_id)},
        content_type="multipart/form-data",
    )
    assert retry_resp.status_code == 200
    retry_body = retry_resp.get_data(as_text=True)
    assert '"type": "delta"' in retry_body
    assert "重试后的完整回复。" in retry_body

    final_messages_resp = client.get(f"/api/conversations/{conv_id}/messages")
    assert final_messages_resp.status_code == 200
    final_messages = final_messages_resp.get_json()["messages"]
    assert [msg["role"] for msg in final_messages] == ["user", "assistant"]
    assert final_messages[1]["content"] == "重试后的完整回复。"
    assert final_messages[1]["status"] == "complete"
    assert len(app.extensions["seen_openai_requests"]) == 2
