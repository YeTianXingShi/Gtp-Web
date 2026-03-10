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



def test_google_chat_stream_uses_google_client_and_base_url(app_builder):
    app = app_builder(
        openai_env_text="OPENAI_BASE_URL=\nOPENAI_API_KEY=\nOPENAI_MODELS=\n",
        google_env_text=(
            "GOOGLE_BASE_URL=https://gemini-proxy.example\n"
            "GOOGLE_API_KEY=google-test-key\n"
            "GOOGLE_MODELS=gemini-2.0-flash\n"
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


def test_google_action_payload_generates_assistant_image(app_builder):
    action_payload = (
        '{'
        '"action": "dalle.text2im", '
        '"action_input": "{\\"prompt\\": \\\"一只坐在窗边晒太阳的橘猫\\\"}", '
        '"thought": "用户想看图片，我来生成。"'
        '}'
    )
    app = app_builder(
        google_env_text=(
            "GOOGLE_BASE_URL=\n"
            "GOOGLE_API_KEY=google-test-key\n"
            "GOOGLE_MODELS=gemini-2.0-flash\n"
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
    assert '已为你生成图片，请查看下方结果。' in body

    seen_image_requests = app.extensions["seen_openai_image_requests"]
    assert seen_image_requests
    assert seen_image_requests[0]["prompt"] == "一只坐在窗边晒太阳的橘猫"

    messages_resp = client.get(f"/api/conversations/{conv_id}/messages")
    assert messages_resp.status_code == 200
    messages_data = messages_resp.get_json()
    assistant_message = next(msg for msg in reversed(messages_data["messages"]) if msg["role"] == "assistant")
    assert assistant_message["content"] == "已为你生成图片，请查看下方结果。"
    assert len(assistant_message["attachments"]) == 1
    assert assistant_message["attachments"][0]["is_image"] is True
    assert assistant_message["attachments"][0]["preview_url"]
