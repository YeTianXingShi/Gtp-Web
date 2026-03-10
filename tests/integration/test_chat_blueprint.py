from __future__ import annotations

import io

from docx import Document

PNG_1X1_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?"
    b"\x00\x05\xfe\x02\xfeA\x0f\x95~\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _create_conversation(client) -> int:
    resp = client.post("/api/conversations", json={"model": "gpt-4o-mini"})
    assert resp.status_code == 201
    return int(resp.get_json()["conversation"]["id"])


def test_chat_stream_with_text_attachment(logged_in_client, app):
    conv_id = _create_conversation(logged_in_client)

    resp = logged_in_client.post(
        "/api/chat/stream",
        data={
            "conversation_id": str(conv_id),
            "model": "gpt-4o-mini",
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
            "model": "gpt-4o-mini",
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
            "model": "gpt-4o-mini",
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
            "model": "gpt-4o-mini",
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
