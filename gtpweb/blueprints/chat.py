from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from flask import Blueprint, Response, jsonify, request, session, stream_with_context
from openai import APIStatusError, OpenAIError
from werkzeug.datastructures import FileStorage

from gtpweb.attachments import (
    build_file_text_block,
    build_message_content_for_model,
    build_user_display_content,
    decode_text_bytes,
    extract_document_text,
    infer_mime_type,
    is_excel_attachment,
    is_image_attachment,
    is_text_attachment,
    is_word_attachment,
    load_message_attachments,
    normalize_uploaded_file_name,
    to_data_url,
    validate_attachment,
)
from gtpweb.config import AppConfig
from gtpweb.db import open_db_connection
from gtpweb.openai_stream import extract_status_error_message, extract_text_delta, sse_payload
from gtpweb.runtime_state import get_runtime_state
from gtpweb.user_store import get_user_record
from gtpweb.utils import safe_filename, safe_int

logger = logging.getLogger(__name__)


def _get_current_user(users_file: Path) -> str | None:
    username = session.get("username")
    if not isinstance(username, str) or not username:
        return None
    record = get_user_record(users_file, username)
    if record is None:
        return None
    return str(record["username"])


def create_chat_blueprint(config: AppConfig) -> Blueprint:
    bp = Blueprint("chat", __name__)

    db_file = config.db_file
    users_file = config.users_file
    upload_dir = config.upload_dir

    @bp.post("/api/chat/stream")
    def chat_stream() -> Response:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        runtime_state = get_runtime_state()
        runtime_settings = runtime_state.settings
        openai_client = runtime_state.openai_client
        max_upload_mb = runtime_settings.max_upload_mb
        max_upload_bytes = runtime_settings.max_upload_bytes
        max_attachments_per_message = runtime_settings.max_attachments_per_message
        max_text_file_chars = runtime_settings.max_text_file_chars
        allowed_attachment_exts = runtime_settings.allowed_attachment_exts
        models = runtime_settings.models
        ai_base_url = runtime_settings.ai_base_url

        content_type = request.content_type or ""
        uploaded_files: list[FileStorage] = []
        content = ""
        model = ""
        conversation_id: int | None = None

        if content_type.startswith("multipart/form-data"):
            content = str(request.form.get("content", "")).strip()
            model = str(request.form.get("model", "")).strip()
            conversation_id = safe_int(request.form.get("conversation_id"))
            uploaded_files = [
                file
                for file in request.files.getlist("files")
                if file and isinstance(file, FileStorage) and file.filename
            ]
        else:
            payload = request.get_json(silent=True) or {}
            content = str(payload.get("content", "")).strip()
            model = str(payload.get("model", "")).strip()
            conversation_id = payload.get("conversation_id")
            if not isinstance(conversation_id, int):
                conversation_id = safe_int(conversation_id)

        logger.info(
            "聊天流请求: 用户=%s 会话ID=%s 模型=%s 文本长度=%s 附件数量=%s 请求类型=%s",
            username,
            conversation_id,
            model,
            len(content),
            len(uploaded_files),
            content_type,
        )

        if not content and not uploaded_files:
            return jsonify({"ok": False, "error": "消息内容和附件不能同时为空"}), 400
        if model not in models:
            return jsonify({"ok": False, "error": "无效的模型"}), 400
        if not isinstance(conversation_id, int):
            return jsonify({"ok": False, "error": "conversation_id 无效"}), 400
        if len(uploaded_files) > max_attachments_per_message:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": f"单次最多上传 {max_attachments_per_message} 个附件",
                    }
                ),
                400,
            )

        prepared_attachments: list[dict[str, Any]] = []
        for file in uploaded_files:
            raw = file.read()
            if not raw:
                logger.warning("附件为空，已忽略: 原始文件名=%s", file.filename)
                continue
            if len(raw) > max_upload_bytes:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": f"文件 {file.filename} 超过 {max_upload_mb}MB 限制",
                        }
                    ),
                    400,
                )

            file_name = normalize_uploaded_file_name(
                file.filename or "",
                f"file_{uuid4().hex[:8]}",
            )
            mime_type = (file.mimetype or "").strip().lower()
            if not mime_type or mime_type == "application/octet-stream":
                mime_type = infer_mime_type(file_name)

            ok, error_message = validate_attachment(file_name, mime_type, allowed_attachment_exts)
            if not ok:
                logger.warning(
                    "附件校验失败: 文件=%s MIME=%s 原因=%s",
                    file_name,
                    mime_type,
                    error_message,
                )
                return jsonify({"ok": False, "error": error_message}), 400

            parsed_text = ""
            kind = "binary"
            content_part: dict[str, Any]

            if is_image_attachment(file_name, mime_type):
                kind = "image"
                content_part = {
                    "type": "image_url",
                    "image_url": {"url": to_data_url(raw, mime_type)},
                }
            elif is_word_attachment(file_name) or is_excel_attachment(file_name):
                kind = "text"
                try:
                    extracted = extract_document_text(file_name, raw)
                except Exception as exc:
                    logger.exception(
                        "附件解析异常: 文件=%s MIME=%s",
                        file_name,
                        mime_type,
                    )
                    return jsonify({"ok": False, "error": f"文件解析失败（{file_name}）：{exc}"}), 400
                parsed_text = build_file_text_block(file_name, extracted, max_text_file_chars)
                content_part = {"type": "text", "text": parsed_text}
            elif is_text_attachment(file_name, mime_type):
                kind = "text"
                text = decode_text_bytes(raw)
                parsed_text = build_file_text_block(file_name, text, max_text_file_chars)
                content_part = {"type": "text", "text": parsed_text}
            else:
                parsed_text = f"[二进制文件未解析: {file_name}]"
                content_part = {"type": "text", "text": parsed_text}

            prepared_attachments.append(
                {
                    "file_name": file_name,
                    "mime_type": mime_type,
                    "kind": kind,
                    "raw": raw,
                    "parsed_text": parsed_text,
                    "content_part": content_part,
                }
            )
            logger.info(
                "附件处理完成: 文件=%s MIME=%s 类型=%s 大小字节=%s 解析文本长度=%s",
                file_name,
                mime_type,
                kind,
                len(raw),
                len(parsed_text),
            )

        if not content and not prepared_attachments:
            return jsonify({"ok": False, "error": "未检测到有效附件内容"}), 400

        file_names_for_display = [str(item["file_name"]) for item in prepared_attachments]
        display_content = build_user_display_content(content, file_names_for_display) or "附件消息"
        completion_messages: list[dict[str, Any]] = []
        with open_db_connection(db_file) as conn:
            conv = conn.execute(
                """
                SELECT id, title
                FROM conversations
                WHERE id = ? AND username = ?
                """,
                (conversation_id, username),
            ).fetchone()
            if conv is None:
                return jsonify({"ok": False, "error": "会话不存在"}), 404

            count_row = conn.execute(
                "SELECT COUNT(1) AS total FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            existing_count = count_row["total"] if count_row else 0
            history_rows = conn.execute(
                """
                SELECT id, role, content
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                """,
                (conversation_id,),
            ).fetchall()
            for row in history_rows:
                msg_attachments = load_message_attachments(conn, int(row["id"]))
                msg_content = build_message_content_for_model(
                    role=str(row["role"]),
                    content=str(row["content"]),
                    attachments=msg_attachments,
                    max_text_file_chars=max_text_file_chars,
                )
                completion_messages.append({"role": str(row["role"]), "content": msg_content})
            logger.info(
                "历史消息加载完成: 会话ID=%s 历史消息数=%s 本次附件数=%s",
                conversation_id,
                len(history_rows),
                len(prepared_attachments),
            )

            cursor = conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (?, 'user', ?)
                """,
                (conversation_id, display_content),
            )
            user_message_id = int(cursor.lastrowid)
            if prepared_attachments:
                user_upload_dir = upload_dir / safe_filename(username) / str(conversation_id)
                user_upload_dir.mkdir(parents=True, exist_ok=True)
                for item in prepared_attachments:
                    saved_name = f"{uuid4().hex}_{item['file_name']}"
                    saved_path = user_upload_dir / saved_name
                    saved_path.write_bytes(item["raw"])
                    conn.execute(
                        """
                        INSERT INTO message_attachments (
                            message_id, file_name, file_path, mime_type, kind, parsed_text
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_message_id,
                            item["file_name"],
                            str(saved_path),
                            item["mime_type"],
                            item["kind"],
                            item["parsed_text"],
                        ),
                    )

            current_user_parts: list[dict[str, Any]] = []
            if content:
                current_user_parts.append({"type": "text", "text": content})
            for item in prepared_attachments:
                current_user_parts.append(item["content_part"])

            if len(current_user_parts) == 1 and current_user_parts[0]["type"] == "text":
                completion_messages.append({"role": "user", "content": current_user_parts[0]["text"]})
            elif current_user_parts:
                completion_messages.append({"role": "user", "content": current_user_parts})
            else:
                completion_messages.append({"role": "user", "content": content})

            updated_title = conv["title"]
            if existing_count == 0 and conv["title"] == "新对话":
                title_seed = content.strip() if content.strip() else display_content
                updated_title = title_seed[:30] if title_seed else "新对话"

            conn.execute(
                """
                UPDATE conversations
                SET title = ?, model = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (updated_title, model, conversation_id),
            )
            conn.commit()
            logger.info(
                "用户消息落库完成: 会话ID=%s 用户消息ID=%s",
                conversation_id,
                user_message_id,
            )

        def generate() -> Any:
            assistant_parts: list[str] = []
            has_error = False
            client_disconnected = False
            delta_count = 0
            started_at = time.perf_counter()
            request_kwargs: dict[str, Any] = {
                "model": model,
                "messages": completion_messages,
                "stream": True,
            }
            logger.info(
                "开始调用上游模型: 会话ID=%s 模型=%s 上下文消息数=%s",
                conversation_id,
                model,
                len(completion_messages),
            )

            try:
                stream = openai_client.chat.completions.create(**request_kwargs)
                for event_obj in stream:
                    delta = extract_text_delta(event_obj)
                    if delta:
                        assistant_parts.append(delta)
                        delta_count += 1
                        if delta_count % 20 == 0:
                            logger.debug(
                                "流式返回进度: 会话ID=%s 分片数=%s 已累计字符=%s",
                                conversation_id,
                                delta_count,
                                len("".join(assistant_parts)),
                            )
                        yield sse_payload({"type": "delta", "text": delta})

                if not assistant_parts and not has_error:
                    has_error = True
                    yield sse_payload(
                        {
                            "type": "error",
                            "error": "请求上游成功但未收到流式文本，请确认网关支持 chat.completions 流式。",
                        }
                    )
                logger.info(
                    "上游模型调用完成: 会话ID=%s 分片数=%s 输出字符=%s 耗时毫秒=%.2f",
                    conversation_id,
                    delta_count,
                    len("".join(assistant_parts)),
                    (time.perf_counter() - started_at) * 1000,
                )

            except APIStatusError as exc:
                has_error = True
                status_code, message = extract_status_error_message(exc)
                status = status_code if status_code is not None else "unknown"
                logger.warning(
                    "上游接口错误: 会话ID=%s 状态=%s 信息=%s",
                    conversation_id,
                    status,
                    message,
                )
                yield sse_payload({"type": "error", "error": f"{ai_base_url} ({status}): {message}"})
            except GeneratorExit:
                client_disconnected = True
                logger.info("聊天流连接已断开: 会话ID=%s（客户端可能已关闭连接）", conversation_id)
                raise
            except OpenAIError as exc:
                has_error = True
                logger.exception("OpenAI SDK 调用异常: 会话ID=%s", conversation_id)
                yield sse_payload({"type": "error", "error": f"AI SDK 调用失败: {exc}"})
            except Exception as exc:
                has_error = True
                logger.exception("聊天流内部异常: 会话ID=%s", conversation_id)
                yield sse_payload({"type": "error", "error": f"服务内部错误: {exc}"})
            finally:
                assistant_text = "".join(assistant_parts).strip()
                if assistant_text:
                    with open_db_connection(db_file) as conn:
                        conn.execute(
                            """
                            INSERT INTO messages (conversation_id, role, content)
                            VALUES (?, 'assistant', ?)
                            """,
                            (conversation_id, assistant_text),
                        )
                        conn.execute(
                            """
                            UPDATE conversations
                            SET updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                            """,
                            (conversation_id,),
                        )
                        conn.commit()
                    logger.info(
                        "助手消息落库完成: 会话ID=%s 字符数=%s",
                        conversation_id,
                        len(assistant_text),
                    )
                    if not client_disconnected:
                        yield sse_payload({"type": "done", "reply": assistant_text})
                else:
                    if (not has_error) and (not client_disconnected):
                        yield sse_payload({"type": "error", "error": "AI 服务返回空结果"})
                    logger.warning(
                        "助手消息为空: 会话ID=%s 是否已有错误=%s",
                        conversation_id,
                        has_error,
                    )
                    if not client_disconnected:
                        yield sse_payload({"type": "done", "reply": ""})

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return bp
