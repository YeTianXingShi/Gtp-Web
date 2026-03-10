from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, jsonify, request, send_file, session

from gtpweb.config import AppConfig
from gtpweb.db import open_db_connection
from gtpweb.utils import safe_filename

logger = logging.getLogger(__name__)


def _get_current_user() -> str | None:
    username = session.get("username")
    return username if isinstance(username, str) and username else None


def create_conversation_blueprint(config: AppConfig) -> Blueprint:
    bp = Blueprint("conversation", __name__)

    db_file = config.db_file
    models = config.models

    @bp.get("/api/conversations")
    def list_conversations() -> Any:
        username = _get_current_user()
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401
        query = str(request.args.get("q", "")).strip()
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
                            AND m.content LIKE ?
                        )
                      )
                    ORDER BY c.updated_at DESC, c.id DESC
                    """,
                    (username, like_query, like_query),
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
            {
                "id": row["id"],
                "title": row["title"],
                "model": row["model"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
        logger.info("会话列表查询完成: 用户=%s 会话数=%s", username, len(conversations))
        return jsonify({"ok": True, "conversations": conversations})

    @bp.delete("/api/conversations/<int:conversation_id>")
    def delete_conversation(conversation_id: int) -> Any:
        username = _get_current_user()
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
        username = _get_current_user()
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

        return jsonify(
            {
                "ok": True,
                "conversation": {
                    "id": updated["id"],
                    "title": updated["title"],
                    "model": updated["model"],
                    "created_at": updated["created_at"],
                    "updated_at": updated["updated_at"],
                },
            }
        )

    @bp.post("/api/conversations")
    def create_conversation() -> Any:
        username = _get_current_user()
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        payload = request.get_json(silent=True) or {}
        model = str(payload.get("model", models[0])).strip() or models[0]
        logger.info("创建会话请求: 用户=%s 模型=%s", username, model)
        if model not in models:
            return jsonify({"ok": False, "error": "无效的模型"}), 400

        title = str(payload.get("title", "新对话")).strip() or "新对话"
        with open_db_connection(db_file) as conn:
            cursor = conn.execute(
                """
                INSERT INTO conversations (username, title, model)
                VALUES (?, ?, ?)
                """,
                (username, title[:60], model),
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
                    "conversation": {
                        "id": row["id"],
                        "title": row["title"],
                        "model": row["model"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    },
                }
            ),
            201,
        )

    @bp.get("/api/conversations/<int:conversation_id>/messages")
    def list_messages(conversation_id: int) -> Any:
        username = _get_current_user()
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
                SELECT id, role, content, created_at
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
        return jsonify({"ok": True, "model": conv["model"], "messages": messages})

    @bp.get("/api/attachments/<int:attachment_id>/content")
    def get_attachment_content(attachment_id: int) -> Response:
        username = _get_current_user()
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
        username = _get_current_user()
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
                SELECT id, role, content, created_at
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
        for row in rows:
            msg_id = int(row["id"])
            messages.append(
                {
                    "role": row["role"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "attachments": attachment_map.get(msg_id, []),
                }
            )
        filename_base = safe_filename(str(conv["title"]))
        logger.info(
            "导出会话准备完成: 用户=%s 会话ID=%s 消息数=%s 附件消息数=%s",
            username,
            conversation_id,
            len(messages),
            sum(1 for msg in messages if msg.get("attachments")),
        )
        if export_format == "txt":
            role_map = {"user": "User", "assistant": "Assistant", "system": "System"}
            lines = [
                f"Title: {conv['title']}",
                f"Model: {conv['model']}",
                f"Created At: {conv['created_at']}",
                f"Updated At: {conv['updated_at']}",
                "",
            ]
            for msg in messages:
                role_label = role_map.get(msg["role"], msg["role"])
                lines.append(f"[{msg['created_at']}] {role_label}:")
                lines.append(str(msg["content"]))
                for att in msg.get("attachments", []):
                    lines.append(
                        f"- Attachment: {att['file_name']} ({att['kind']}, {att['mime_type']})"
                    )
                lines.append("")
            body = "\n".join(lines)
            return Response(
                body,
                mimetype="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename_base}.txt"',
                },
            )

        body = json.dumps(
            {
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
