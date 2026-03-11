from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, jsonify, request, send_file, session

from gtpweb.ai_providers import normalize_model_selection, resolve_model_option
from gtpweb.config import AppConfig
from gtpweb.db import open_db_connection
from gtpweb.runtime_state import get_runtime_state
from gtpweb.user_store import get_user_record
from gtpweb.utils import safe_filename

logger = logging.getLogger(__name__)


def _get_current_user(users_file: Path) -> str | None:
    username = session.get("username")
    if not isinstance(username, str) or not username:
        return None
    record = get_user_record(users_file, username)
    if record is None:
        return None
    return str(record["username"])


def _serialize_conversation_row(row: Any, normalized_model: str) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "model": normalized_model,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


_ROLE_LABELS = {"user": "用户", "assistant": "助手", "system": "系统"}


def _get_role_label(role: str) -> str:
    return _ROLE_LABELS.get(role, role)


def _get_exported_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_export_message(
    *,
    row: Any,
    attachments: list[dict[str, Any]],
    index: int,
) -> dict[str, Any]:
    role = str(row["role"])
    reasoning = str(row["reasoning"] or "")
    return {
        "id": int(row["id"]),
        "index": index,
        "role": role,
        "role_label": _get_role_label(role),
        "content": str(row["content"] or ""),
        "reasoning": reasoning,
        "has_reasoning": bool(reasoning),
        "created_at": row["created_at"],
        "attachments": attachments,
    }


def _build_txt_export_body(
    *,
    conversation: Any,
    messages: list[dict[str, Any]],
    exported_at: str,
) -> str:
    attachment_count = sum(len(msg.get("attachments", [])) for msg in messages)
    lines = [
        f"会话标题：{conversation['title']}",
        f"模型：{conversation['model']}",
        f"创建时间：{conversation['created_at']}",
        f"更新时间：{conversation['updated_at']}",
        f"导出时间：{exported_at}",
        f"消息总数：{len(messages)}",
        f"附件总数：{attachment_count}",
        "",
    ]

    for msg in messages:
        lines.append(f"### 第 {msg['index']} 条｜{msg['role_label']}｜{msg['created_at']}")
        lines.append("回复：")
        lines.append(str(msg["content"]))
        if msg.get("has_reasoning"):
            lines.append("")
            lines.append("思考摘要：")
            lines.append(str(msg["reasoning"]))
        if msg.get("attachments"):
            lines.append("")
            lines.append("附件：")
            for attachment in msg["attachments"]:
                lines.append(
                    f"- {attachment['file_name']}（{attachment['kind']}，{attachment['mime_type']}）"
                )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def create_conversation_blueprint(config: AppConfig) -> Blueprint:
    bp = Blueprint("conversation", __name__)

    db_file = config.db_file
    users_file = config.users_file

    @bp.get("/api/conversations")
    def list_conversations() -> Any:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401
        query = str(request.args.get("q", "")).strip()
        runtime_settings = get_runtime_state().settings
        logger.info("会话列表查询: 用户=%s 关键词长度=%s", username, len(query))

        with open_db_connection(db_file) as conn:
            if query:
                like_query = f"%{query}%"
                rows = conn.execute(
                    """
                    SELECT c.id, c.title, c.model, c.created_at, c.updated_at
                    FROM conversations c
                    WHERE c.username = ?
                      AND (
                        c.title LIKE ?
                        OR EXISTS (
                          SELECT 1
                          FROM messages m
                          WHERE m.conversation_id = c.id
                            AND (
                              m.content LIKE ?
                              OR m.reasoning LIKE ?
                            )
                        )
                      )
                    ORDER BY c.updated_at DESC, c.id DESC
                    """,
                    (username, like_query, like_query, like_query),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, title, model, created_at, updated_at
                    FROM conversations
                    WHERE username = ?
                    ORDER BY updated_at DESC, id DESC
                    """,
                    (username,),
                ).fetchall()

        conversations = [
            _serialize_conversation_row(
                row,
                normalize_model_selection(
                    str(row["model"]),
                    runtime_settings.model_options,
                    fallback_to_first=True,
                ),
            )
            for row in rows
        ]
        logger.info("会话列表查询完成: 用户=%s 会话数=%s", username, len(conversations))
        return jsonify({"ok": True, "conversations": conversations})

    @bp.delete("/api/conversations/<int:conversation_id>")
    def delete_conversation(conversation_id: int) -> Any:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401
        logger.info("删除会话请求: 用户=%s 会话ID=%s", username, conversation_id)

        with open_db_connection(db_file) as conn:
            row = conn.execute(
                """
                SELECT id
                FROM conversations
                WHERE id = ? AND username = ?
                """,
                (conversation_id, username),
            ).fetchone()
            if row is None:
                logger.warning("删除会话失败: 会话不存在 用户=%s 会话ID=%s", username, conversation_id)
                return jsonify({"ok": False, "error": "会话不存在"}), 404

            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            conn.commit()
        logger.info("删除会话完成: 用户=%s 会话ID=%s", username, conversation_id)

        return jsonify({"ok": True})

    @bp.patch("/api/conversations/<int:conversation_id>")
    def rename_conversation(conversation_id: int) -> Any:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        payload = request.get_json(silent=True) or {}
        title = str(payload.get("title", "")).strip()
        logger.info(
            "重命名会话请求: 用户=%s 会话ID=%s 新标题长度=%s",
            username,
            conversation_id,
            len(title),
        )
        if not title:
            return jsonify({"ok": False, "error": "会话名称不能为空"}), 400
        title = title[:60]

        with open_db_connection(db_file) as conn:
            row = conn.execute(
                """
                SELECT id
                FROM conversations
                WHERE id = ? AND username = ?
                """,
                (conversation_id, username),
            ).fetchone()
            if row is None:
                logger.warning("重命名会话失败: 会话不存在 用户=%s 会话ID=%s", username, conversation_id)
                return jsonify({"ok": False, "error": "会话不存在"}), 404

            conn.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (title, conversation_id),
            )
            conn.commit()

            updated = conn.execute(
                """
                SELECT id, title, model, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        logger.info("重命名会话完成: 用户=%s 会话ID=%s 新标题=%s", username, conversation_id, updated["title"])

        runtime_settings = get_runtime_state().settings
        return jsonify(
            {
                "ok": True,
                "conversation": _serialize_conversation_row(
                    updated,
                    normalize_model_selection(
                        str(updated["model"]),
                        runtime_settings.model_options,
                        fallback_to_first=True,
                    ),
                ),
            }
        )

    @bp.post("/api/conversations")
    def create_conversation() -> Any:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        runtime_settings = get_runtime_state().settings

        payload = request.get_json(silent=True) or {}
        requested_model = str(payload.get("model", runtime_settings.models[0])).strip() or runtime_settings.models[0]
        model_option = resolve_model_option(requested_model, runtime_settings.model_options)
        logger.info("创建会话请求: 用户=%s 模型=%s", username, requested_model)
        if model_option is None:
            return jsonify({"ok": False, "error": "无效的模型"}), 400

        title = str(payload.get("title", "新对话")).strip() or "新对话"
        with open_db_connection(db_file) as conn:
            cursor = conn.execute(
                """
                INSERT INTO conversations (username, title, model)
                VALUES (?, ?, ?)
                """,
                (username, title[:60], model_option.id),
            )
            conversation_id = cursor.lastrowid
            conn.commit()

            row = conn.execute(
                """
                SELECT id, title, model, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        logger.info("创建会话完成: 用户=%s 会话ID=%s 标题=%s", username, row["id"], row["title"])

        return (
            jsonify(
                {
                    "ok": True,
                    "conversation": _serialize_conversation_row(row, model_option.id),
                }
            ),
            201,
        )

    @bp.get("/api/conversations/<int:conversation_id>/messages")
    def list_messages(conversation_id: int) -> Any:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401
        logger.info("查询消息列表: 用户=%s 会话ID=%s", username, conversation_id)

        with open_db_connection(db_file) as conn:
            conv = conn.execute(
                """
                SELECT id, model
                FROM conversations
                WHERE id = ? AND username = ?
                """,
                (conversation_id, username),
            ).fetchone()
            if conv is None:
                logger.warning("查询消息失败: 会话不存在 用户=%s 会话ID=%s", username, conversation_id)
                return jsonify({"ok": False, "error": "会话不存在"}), 404

            rows = conn.execute(
                """
                SELECT id, role, content, reasoning, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                """,
                (conversation_id,),
            ).fetchall()

            message_ids = [int(row["id"]) for row in rows]
            attachment_map: dict[int, list[dict[str, Any]]] = {message_id: [] for message_id in message_ids}
            if message_ids:
                placeholders = ",".join(["?"] * len(message_ids))
                attachment_rows = conn.execute(
                    f"""
                    SELECT id, message_id, file_name, mime_type, kind, created_at
                    FROM message_attachments
                    WHERE message_id IN ({placeholders})
                    ORDER BY id ASC
                    """,
                    tuple(message_ids),
                ).fetchall()
                for att in attachment_rows:
                    is_image = str(att["kind"]) == "image"
                    attachment_map[int(att["message_id"])].append(
                        {
                            "id": att["id"],
                            "file_name": att["file_name"],
                            "mime_type": att["mime_type"],
                            "kind": att["kind"],
                            "is_image": is_image,
                            "preview_url": (
                                f"/api/attachments/{att['id']}/content" if is_image else None
                            ),
                            "created_at": att["created_at"],
                        }
                    )

        messages = []
        for row in rows:
            msg_id = int(row["id"])
            messages.append(
                {
                    "id": msg_id,
                    "role": row["role"],
                    "content": row["content"],
                    "reasoning": row["reasoning"],
                    "created_at": row["created_at"],
                    "attachments": attachment_map.get(msg_id, []),
                }
            )
        logger.info(
            "查询消息列表完成: 用户=%s 会话ID=%s 消息数=%s",
            username,
            conversation_id,
            len(messages),
        )
        runtime_settings = get_runtime_state().settings
        return jsonify(
            {
                "ok": True,
                "model": normalize_model_selection(
                    str(conv["model"]),
                    runtime_settings.model_options,
                    fallback_to_first=True,
                ),
                "messages": messages,
            }
        )

    @bp.get("/api/attachments/<int:attachment_id>/content")
    def get_attachment_content(attachment_id: int) -> Response:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401
        logger.info("读取附件内容请求: 用户=%s 附件ID=%s", username, attachment_id)

        with open_db_connection(db_file) as conn:
            row = conn.execute(
                """
                SELECT ma.id, ma.file_name, ma.file_path, ma.mime_type
                FROM message_attachments ma
                JOIN messages m ON m.id = ma.message_id
                JOIN conversations c ON c.id = m.conversation_id
                WHERE ma.id = ? AND c.username = ?
                """,
                (attachment_id, username),
            ).fetchone()

        if row is None:
            logger.warning("读取附件失败: 附件不存在或无权限 用户=%s 附件ID=%s", username, attachment_id)
            return jsonify({"ok": False, "error": "附件不存在"}), 404

        file_path = Path(str(row["file_path"]))
        if not file_path.exists():
            logger.warning(
                "读取附件失败: 文件缺失 用户=%s 附件ID=%s 路径=%s",
                username,
                attachment_id,
                file_path,
            )
            return jsonify({"ok": False, "error": "附件文件不存在"}), 404

        logger.info("读取附件成功: 用户=%s 附件ID=%s 文件=%s", username, attachment_id, row["file_name"])
        return send_file(
            file_path,
            mimetype=str(row["mime_type"] or "application/octet-stream"),
            as_attachment=False,
            download_name=str(row["file_name"]),
            conditional=True,
        )

    @bp.get("/api/conversations/<int:conversation_id>/export")
    def export_conversation(conversation_id: int) -> Response:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        export_format = str(request.args.get("format", "json")).strip().lower()
        logger.info(
            "导出会话请求: 用户=%s 会话ID=%s 格式=%s",
            username,
            conversation_id,
            export_format,
        )
        if export_format not in {"json", "txt"}:
            return jsonify({"ok": False, "error": "不支持的导出格式"}), 400

        with open_db_connection(db_file) as conn:
            conv = conn.execute(
                """
                SELECT id, title, model, created_at, updated_at
                FROM conversations
                WHERE id = ? AND username = ?
                """,
                (conversation_id, username),
            ).fetchone()
            if conv is None:
                logger.warning("导出会话失败: 会话不存在 用户=%s 会话ID=%s", username, conversation_id)
                return jsonify({"ok": False, "error": "会话不存在"}), 404

            rows = conn.execute(
                """
                SELECT id, role, content, reasoning, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                """,
                (conversation_id,),
            ).fetchall()

            message_ids = [int(row["id"]) for row in rows]
            attachment_map: dict[int, list[dict[str, Any]]] = {message_id: [] for message_id in message_ids}
            if message_ids:
                placeholders = ",".join(["?"] * len(message_ids))
                attachment_rows = conn.execute(
                    f"""
                    SELECT message_id, file_name, mime_type, kind, created_at
                    FROM message_attachments
                    WHERE message_id IN ({placeholders})
                    ORDER BY id ASC
                    """,
                    tuple(message_ids),
                ).fetchall()
                for att in attachment_rows:
                    attachment_map[int(att["message_id"])].append(
                        {
                            "file_name": att["file_name"],
                            "mime_type": att["mime_type"],
                            "kind": att["kind"],
                            "created_at": att["created_at"],
                        }
                    )

        messages = []
        for index, row in enumerate(rows, start=1):
            msg_id = int(row["id"])
            messages.append(
                _build_export_message(
                    row=row,
                    attachments=attachment_map.get(msg_id, []),
                    index=index,
                )
            )
        filename_base = safe_filename(str(conv["title"]))
        exported_at = _get_exported_at()
        attachment_count = sum(len(msg.get("attachments", [])) for msg in messages)
        reasoning_message_count = sum(1 for msg in messages if msg.get("has_reasoning"))
        logger.info(
            "导出会话准备完成: 用户=%s 会话ID=%s 消息数=%s 附件消息数=%s",
            username,
            conversation_id,
            len(messages),
            sum(1 for msg in messages if msg.get("attachments")),
        )
        if export_format == "txt":
            body = _build_txt_export_body(
                conversation=conv,
                messages=messages,
                exported_at=exported_at,
            )
            return Response(
                body,
                mimetype="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename_base}.txt"',
                },
            )

        body = json.dumps(
            {
                "export_meta": {
                    "format_version": 2,
                    "exported_at": exported_at,
                    "message_count": len(messages),
                    "attachment_count": attachment_count,
                    "reasoning_message_count": reasoning_message_count,
                },
                "conversation": {
                    "id": conv["id"],
                    "title": conv["title"],
                    "model": conv["model"],
                    "created_at": conv["created_at"],
                    "updated_at": conv["updated_at"],
                },
                "messages": messages,
            },
            ensure_ascii=False,
            indent=2,
        )
        return Response(
            body,
            mimetype="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename_base}.json"',
            },
        )

    return bp
