from __future__ import annotations


def test_conversation_crud(logged_in_client):
    create_resp = logged_in_client.post("/api/conversations", json={"model": "gpt-4o-mini"})
    assert create_resp.status_code == 201
    conv_id = create_resp.get_json()["conversation"]["id"]

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
