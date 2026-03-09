from __future__ import annotations

import io

from docx import Document


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
