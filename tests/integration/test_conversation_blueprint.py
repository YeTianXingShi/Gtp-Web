from __future__ import annotations

import json


def _create_conversation(client, model: str = "openai:gpt-4o-mini") -> int:
    create_resp = client.post("/api/conversations", json={"model": model})
    assert create_resp.status_code == 201
    return int(create_resp.get_json()["conversation"]["id"])


def _create_reasoning_conversation(app_builder):
    app = app_builder(
        openai_env_text=(
            "OPENAI_BASE_URL=https://example.invalid/v1\n"
            "OPENAI_API_KEY=test-key\n"
            "OPENAI_MODELS=gpt-5-mini\n"
            "OPENAI_IMAGE_MODEL=dall-e-3\n"
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

    conv_id = _create_conversation(client, model="openai:gpt-5-mini")
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
    _ = stream_resp.get_data(as_text=True)
    return client, conv_id


def test_conversation_crud(logged_in_client):
    conv_id = _create_conversation(logged_in_client)

    list_resp = logged_in_client.get("/api/conversations")
    assert list_resp.status_code == 200
    assert any(conv["id"] == conv_id for conv in list_resp.get_json()["conversations"])

    rename_resp = logged_in_client.patch(
        f"/api/conversations/{conv_id}",
        json={"title": "重命名会话"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.get_json()["conversation"]["title"] == "重命名会话"

    delete_resp = logged_in_client.delete(f"/api/conversations/{conv_id}")
    assert delete_resp.status_code == 200


def test_export_json_includes_reasoning_metadata(app_builder):
    client, conv_id = _create_reasoning_conversation(app_builder)

    export_resp = client.get(f"/api/conversations/{conv_id}/export?format=json")
    assert export_resp.status_code == 200
    data = json.loads(export_resp.get_data(as_text=True))

    assert data["export_meta"]["format_version"] == 2
    assert data["export_meta"]["message_count"] == 2
    assert data["export_meta"]["attachment_count"] == 0
    assert data["export_meta"]["reasoning_message_count"] == 1
    assert data["export_meta"]["exported_at"].endswith("Z")

    assistant_message = next(msg for msg in data["messages"] if msg["role"] == "assistant")
    assert assistant_message["id"] > 0
    assert assistant_message["index"] == 2
    assert assistant_message["role_label"] == "助手"
    assert assistant_message["content"] == "这是最终回复。"
    assert assistant_message["reasoning"] == "先整理已知条件。再给出结论。"
    assert assistant_message["has_reasoning"] is True


def test_export_txt_uses_grouped_reasoning_layout(app_builder):
    client, conv_id = _create_reasoning_conversation(app_builder)

    export_resp = client.get(f"/api/conversations/{conv_id}/export?format=txt")
    assert export_resp.status_code == 200
    body = export_resp.get_data(as_text=True)

    assert "会话标题：" in body
    assert "导出时间：" in body
    assert "消息总数：2" in body
    assert "### 第 2 条｜助手｜" in body
    assert "回复：" in body
    assert "这是最终回复。" in body
    assert "思考摘要：" in body
    assert "先整理已知条件。再给出结论。" in body


def test_export_uses_ascii_safe_content_disposition_for_unicode_title(logged_in_client):
    conv_id = _create_conversation(logged_in_client)

    rename_resp = logged_in_client.patch(
        f"/api/conversations/{conv_id}",
        json={"title": "中文会话标题"},
    )
    assert rename_resp.status_code == 200

    export_resp = logged_in_client.get(f"/api/conversations/{conv_id}/export?format=json")
    assert export_resp.status_code == 200

    disposition = export_resp.headers["Content-Disposition"]
    disposition.encode("latin-1")
    assert "filename*=UTF-8''" in disposition
    assert 'filename="download.json"' in disposition
    assert "%E4%B8%AD%E6%96%87%E4%BC%9A%E8%AF%9D%E6%A0%87%E9%A2%98.json" in disposition
