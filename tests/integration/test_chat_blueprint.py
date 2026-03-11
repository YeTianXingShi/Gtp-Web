from __future__ import annotations

import io

from docx import Document

PNG_1X1_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?"
    b"\x00\x05\xfe\x02\xfeA\x0f\x95~\x00\x00\x00\x00IEND\xaeB`\x82"
)



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
            '  "openai": {"image_model": "", "models": []},\n'
            '  "google": {"image_model": "", "models": [{"name": "gemini-2.0-flash", "thinking": false}]}\n'
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



def test_google_action_payload_generates_assistant_image_with_openai_provider(app_builder):
    action_payload = (
        '{'
        '"action": "dalle.text2im", '
        '"action_input": "{\\"prompt\\": \\\"一只坐在窗边晒太阳的橘猫\\\"}", '
        '"thought": "用户想看图片，我来生成。"'
        '}'
    )
    app = app_builder(
        models_config_text=(
            '{\n'
            '  "openai": {"image_model": "dall-e-3", "models": [{"name": "gpt-4o-mini"}]},\n'
            '  "google": {"image_model": "", "models": [{"name": "gemini-2.0-flash", "thinking": false}]}\n'
            '}\n'
        ),
        google_env_text=(
            "GOOGLE_BASE_URL=\n"
            "GOOGLE_API_KEY=google-test-key\n"
        ),
        google_stream_text=action_payload,
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

    stream_resp = client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "google:gemini-2.0-flash",
            "content": "帮我画一只猫",
        },
        content_type="multipart/form-data",
    )
    assert stream_resp.status_code == 200
    body = stream_resp.get_data(as_text=True)
    assert "已为你生成图片，请查看下方结果。" in body

    seen_openai_image_requests = app.extensions["seen_openai_image_requests"]
    assert seen_openai_image_requests
    assert seen_openai_image_requests[0]["model"] == "dall-e-3"
    assert seen_openai_image_requests[0]["prompt"] == "一只坐在窗边晒太阳的橘猫"

    seen_google_image_requests = app.extensions["seen_google_image_requests"]
    assert seen_google_image_requests == []

    seen_google_content_image_requests = app.extensions["seen_google_content_image_requests"]
    assert seen_google_content_image_requests == []

    messages_resp = client.get(f"/api/conversations/{conv_id}/messages")
    assert messages_resp.status_code == 200
    messages_data = messages_resp.get_json()
    assistant_message = next(msg for msg in reversed(messages_data["messages"]) if msg["role"] == "assistant")
    assert assistant_message["content"] == "已为你生成图片，请查看下方结果。"
    assert len(assistant_message["attachments"]) == 1
    assert assistant_message["attachments"][0]["is_image"] is True
    assert assistant_message["attachments"][0]["preview_url"]


def test_openai_reasoning_summary_is_persisted_in_messages(app_builder):
    app = app_builder(
        models_config_text=(
            '{\n'
            '  "openai": {\n'
            '    "image_model": "dall-e-3",\n'
            '    "models": [{"name": "gpt-5-mini", "reasoning": {"effort": "high", "summary": "auto"}}]\n'
            '  },\n'
            '  "google": {"image_model": "", "models": []}\n'
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
            '    "image_model": "",\n'
            '    "defaults": {"reasoning": {"enabled": true, "effort": "high", "summary": "auto"}},\n'
            '    "models": [{"name": "gpt-5-mini", "reasoning": {"enabled": false}}]\n'
            '  },\n'
            '  "google": {"image_model": "", "models": []}\n'
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
            '  "openai": {"image_model": "", "models": []},\n'
            '  "google": {\n'
            '    "image_model": "",\n'
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
            '  "openai": {"image_model": "", "models": []},\n'
            '  "google": {\n'
            '    "image_model": "",\n'
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



def test_google_imagen_model_uses_generate_images(app_builder):
    action_payload = (
        '{'
        '"action": "dalle.text2im", '
        '"action_input": "{\\"prompt\\": \\\"一只雪山前奔跑的白狼\\\", \\\"model\\\": \\\"dall-e-3\\\"}", '
        '"thought": "用户想看图片，我来生成。"'
        '}'
    )
    app = app_builder(
        app_env_text=(
            "APP_SECRET_KEY=test-secret\n"
            "PORT=8000\n"
            "FLASK_DEBUG=1\n"
            "IMAGE_TOOL_PROVIDER=google\n"
        ),
        models_config_text=(
            '{\n'
            '  "openai": {"image_model": "", "models": []},\n'
            '  "google": {"image_model": "imagen-3.0-generate-002", "models": [{"name": "gemini-2.0-flash", "thinking": false}]}\n'
            '}\n'
        ),
        google_env_text=(
            "GOOGLE_BASE_URL=https://gemini-proxy.example\n"
            "GOOGLE_API_KEY=google-test-key\n"
        ),
        google_stream_text=action_payload,
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

    stream_resp = client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "google:gemini-2.0-flash",
            "content": "帮我画一只狼",
        },
        content_type="multipart/form-data",
    )
    assert stream_resp.status_code == 200
    body = stream_resp.get_data(as_text=True)
    assert "已为你生成图片，请查看下方结果。" in body

    seen_google_image_requests = app.extensions["seen_google_image_requests"]
    assert seen_google_image_requests
    assert seen_google_image_requests[0]["model"] == "imagen-3.0-generate-002"
    assert seen_google_image_requests[0]["prompt"] == "一只雪山前奔跑的白狼"

    seen_google_content_image_requests = app.extensions["seen_google_content_image_requests"]
    assert seen_google_content_image_requests == []

    seen_openai_image_requests = app.extensions["seen_openai_image_requests"]
    assert seen_openai_image_requests == []



def test_google_gemini_image_model_uses_generate_content(app_builder):
    action_payload = (
        '{'
        '"action": "dalle.text2im", '
        '"action_input": "{\\"prompt\\": \\\"一座漂浮在云海上的未来城市\\\", \\\"size\\\": \\\"1792x1024\\\"}", '
        '"thought": "用户想看图片，我来生成。"'
        '}'
    )
    app = app_builder(
        app_env_text=(
            "APP_SECRET_KEY=test-secret\n"
            "PORT=8000\n"
            "FLASK_DEBUG=1\n"
            "IMAGE_TOOL_PROVIDER=google\n"
        ),
        models_config_text=(
            '{\n'
            '  "openai": {"image_model": "", "models": []},\n'
            '  "google": {"image_model": "gemini-3.1-flash-image-preview", "models": [{"name": "gemini-2.0-flash", "thinking": false}]}\n'
            '}\n'
        ),
        google_env_text=(
            "GOOGLE_BASE_URL=https://gemini-proxy.example\n"
            "GOOGLE_API_KEY=google-test-key\n"
        ),
        google_stream_text=action_payload,
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

    stream_resp = client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "google:gemini-2.0-flash",
            "content": "帮我画一座未来城市",
        },
        content_type="multipart/form-data",
    )
    assert stream_resp.status_code == 200
    body = stream_resp.get_data(as_text=True)
    assert "已为你生成图片，请查看下方结果。" in body

    seen_google_content_image_requests = app.extensions["seen_google_content_image_requests"]
    assert seen_google_content_image_requests
    assert seen_google_content_image_requests[0]["model"] == "gemini-3.1-flash-image-preview"
    assert seen_google_content_image_requests[0]["contents"] == ["一座漂浮在云海上的未来城市"]

    config = seen_google_content_image_requests[0]["config"]
    assert getattr(config, "response_modalities", None) == ["IMAGE"]
    image_config = getattr(config, "image_config", None)
    assert image_config is not None
    assert getattr(image_config, "aspect_ratio", None) == "16:9"

    seen_google_image_requests = app.extensions["seen_google_image_requests"]
    assert seen_google_image_requests == []

    seen_openai_image_requests = app.extensions["seen_openai_image_requests"]
    assert seen_openai_image_requests == []



def test_empty_image_model_disables_text2im_capability(app_builder):
    action_payload = (
        '{'
        '"action": "dalle.text2im", '
        '"action_input": "{\\"prompt\\": \\\"一只坐在书桌上的猫\\\", \\\"model\\\": \\\"dall-e-3\\\"}", '
        '"thought": "用户想看图片，我来生成。"'
        '}'
    )
    app = app_builder(
        models_config_text=(
            '{\n'
            '  "openai": {"image_model": "", "models": [{"name": "gpt-4o-mini"}]},\n'
            '  "google": {"image_model": "", "models": [{"name": "gemini-2.0-flash", "thinking": false}]}\n'
            '}\n'
        ),
        openai_env_text=(
            "OPENAI_BASE_URL=https://example.invalid/v1\n"
            "OPENAI_API_KEY=test-key\n"
        ),
        google_env_text=(
            "GOOGLE_BASE_URL=\n"
            "GOOGLE_API_KEY=google-test-key\n"
        ),
        google_stream_text=action_payload,
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

    stream_resp = client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "google:gemini-2.0-flash",
            "content": "帮我画一只猫",
        },
        content_type="multipart/form-data",
    )
    assert stream_resp.status_code == 200
    body = stream_resp.get_data(as_text=True)
    assert "模型请求生成图片，但当前系统未启用该能力。" in body

    assert app.extensions["seen_openai_image_requests"] == []
    assert app.extensions["seen_google_image_requests"] == []
    assert app.extensions["seen_google_content_image_requests"] == []
