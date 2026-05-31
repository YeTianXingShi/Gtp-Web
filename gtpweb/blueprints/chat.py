"""
聊天蓝图模块

本模块处理聊天相关的路由和功能，包括：
- 聊天消息发送和流式响应
- 附件处理（图片、文本、文档）
- 消息重试
- 对话管理
- OpenAI 和 Google AI API 集成
"""

from __future__ import annotations

import io
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from flask import Blueprint, Response, g, jsonify, request, stream_with_context
from openai import APIStatusError, OpenAIError
from werkzeug.datastructures import FileStorage

from gtpweb.ai_providers import (
    PROVIDER_CLAUDE,
    PROVIDER_GOOGLE,
    PROVIDER_OPENAI,
    build_claude_messages,
    build_effective_claude_thinking_settings,
    build_effective_google_thinking_settings,
    build_effective_openai_reasoning_settings,
    build_google_generate_content_config,
    build_google_contents,
    extract_google_reasoning_delta,
    extract_google_text_delta,
    normalize_model_selection,
    resolve_conversation_model_settings,
    resolve_model_option,
)
from gtpweb.attachments import (
    build_message_content_for_model,
    build_user_display_content,
    infer_mime_type,
    is_image_attachment,
    load_message_attachments,
    normalize_uploaded_file_name,
    to_data_url,
    validate_attachment,
)
from gtpweb.audit import log_audit
from gtpweb.auth_jwt import require_login
from gtpweb.config import AppConfig
from gtpweb.conversation_titles import generate_conversation_title, is_default_conversation_title
from gtpweb.db import open_db_connection
from gtpweb.openai_stream import (
    build_openai_response_input,
    extract_reasoning_summary_delta,
    extract_status_error_message,
    extract_text_delta,
    sse_payload,
)
from gtpweb.runtime_state import get_runtime_state
from gtpweb.token_tracking import record_token_usage
from gtpweb.user_store import get_user_record
from gtpweb.utils import safe_filename, safe_int

logger = logging.getLogger(__name__)


def _parse_file_to_markdown(file_name: str, mime_type: str, raw: bytes) -> str:
    try:
        from markitdown import MarkItDown, StreamInfo
        from pathlib import Path
        md = MarkItDown()
        ext = Path(file_name).suffix.lower()
        stream_info = StreamInfo(extension=ext, mimetype=mime_type, filename=file_name)
        result = md.convert_stream(io.BytesIO(raw), stream_info=stream_info)
        text = (result.text_content or "").strip()
        if text:
            logger.info("MarkItDown 解析成功: 文件=%s 字符数=%s", file_name, len(text))
        return text
    except Exception:
        logger.warning("MarkItDown 解析失败: 文件=%s MIME=%s", file_name, mime_type, exc_info=True)
        return ""


# 友好错误提示映射：避免把上游 raw 报文（含内部 URL、API Key 提示等）原样返回前端
_PROVIDER_LABEL = {
    PROVIDER_OPENAI: "OpenAI",
    PROVIDER_GOOGLE: "Google Gemini",
    PROVIDER_CLAUDE: "Claude",
}


def _friendly_message_by_status(provider: str, status_code: int | None) -> str:
    """根据 HTTP 状态码返回脱敏后的中文友好提示。"""
    label = _PROVIDER_LABEL.get(provider, "AI 服务")
    if status_code is None:
        return f"{label} 服务暂不可用，请稍后重试"
    if status_code == 401:
        return f"{label} API Key 无效或已过期，请联系管理员检查配置"
    if status_code == 403:
        return f"{label} 拒绝访问，可能是当前账号无权使用该模型，或地区/网络受限"
    if status_code == 404:
        return f"{label} 找不到该模型，可能模型名拼写有误或已下线"
    if status_code == 408:
        return f"{label} 响应超时，请稍后重试"
    if status_code == 429:
        return f"{label} 请求过于频繁或额度已用尽，请稍后重试"
    if status_code == 502:
        return f"{label} 网关错误，可能是附件过大或格式不受支持，请减小文件体积或改用其他模型重试"
    if status_code in (500, 503, 504):
        return f"{label} 服务暂时不可用，请稍后重试"
    if 400 <= status_code < 500:
        return f"{label} 拒绝了本次请求 (HTTP {status_code})，请检查输入或联系管理员"
    return f"{label} 调用失败 (HTTP {status_code})，请稍后重试"


def _extract_anthropic_status(exc: Any) -> tuple[int | None, str | None]:
    """从 anthropic.APIStatusError / 通用 HTTP 异常中提取状态码与 raw 消息（仅用于日志）。"""
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        # anthropic 1.x 可能挂在 .response.status_code
        response = getattr(exc, "response", None)
        if response is not None:
            sc = getattr(response, "status_code", None)
            if isinstance(sc, int):
                status_code = sc
    raw_msg: str | None = None
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err_obj = body.get("error")
        if isinstance(err_obj, dict):
            raw_msg = str(err_obj.get("message") or "")
    if not raw_msg:
        raw_msg = str(exc) or None
    return status_code, raw_msg


def _format_upstream_error(provider: str, exc: BaseException) -> tuple[str, int | None, str]:
    """
    把任意上游异常转成 (前端可见消息, status_code, 日志原文)。
    前端消息已脱敏；status_code 与 raw_message 仅用于服务端日志。
    """
    raw_message = str(exc) or exc.__class__.__name__
    status_code: int | None = None

    # OpenAI APIStatusError
    if isinstance(exc, APIStatusError):
        status_code, raw_message = extract_status_error_message(exc)

    # Anthropic / Claude：通过 duck-typing 检测，避免把 anthropic 设为硬依赖
    elif exc.__class__.__module__.startswith("anthropic"):
        status_code, raw = _extract_anthropic_status(exc)
        if raw:
            raw_message = raw

    # Google google-genai：errors.APIError 系列
    elif exc.__class__.__module__.startswith("google."):
        sc = getattr(exc, "code", None)
        if isinstance(sc, int):
            status_code = sc
        # google-genai 的 APIError 通常 str(exc) 已是 JSON，截断保留前 300 字符做日志
        raw_message = (str(exc) or raw_message)[:500]

    friendly = _friendly_message_by_status(provider, status_code)
    return friendly, status_code, raw_message


_TITLE_UPDATE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="title-update")


def _build_openai_reasoning_config(
    *,
    reasoning_settings: Any,
) -> dict[str, Any] | None:
    """
    构建 OpenAI 推理配置

    Args:
        reasoning_settings: OpenAI 推理设置对象

    Returns:
        推理配置字典，如果推理未启用则返回 None
    """
    if reasoning_settings is None or not getattr(reasoning_settings, "enabled", True):
        return None

    config: dict[str, Any] = {}
    effort = str(getattr(reasoning_settings, "effort", "") or "").strip().lower()
    summary = str(getattr(reasoning_settings, "summary", "") or "").strip().lower()
    if effort:
        config["effort"] = effort
    if summary:
        config["summary"] = summary
    return config or None


def _get_current_username() -> str:
    """从 g 读取当前用户名。需配合 @require_login 使用。"""
    return str(g.user["username"])


def _insert_message_attachments(
    conn: Any,
    *,
    message_id: int,
    attachments: list[dict[str, Any]],
) -> None:
    for item in attachments:
        conn.execute(
            """
            INSERT INTO message_attachments (
                message_id, file_name, file_path, mime_type, kind, parsed_text
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                item["file_name"],
                item["file_path"],
                item["mime_type"],
                item["kind"],
                item.get("parsed_text", ""),
            ),
        )


def _save_assistant_message(
    *,
    db_file: Path,
    conversation_id: int,
    content: str,
    reasoning: str,
    attachments: list[dict[str, Any]],
    status: str,
) -> None:
    with open_db_connection(db_file) as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, reasoning, status)
            VALUES (?, 'assistant', ?, ?, ?)
            """,
            (conversation_id, content, reasoning, status),
        )
        assistant_message_id = int(cursor.lastrowid)
        if attachments:
            _insert_message_attachments(
                conn,
                message_id=assistant_message_id,
                attachments=attachments,
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



def _maybe_update_conversation_title(
    *,
    db_file: Path,
    conversation_id: int,
    current_title: str,
    completion_messages: list[dict[str, Any]],
    selected_provider: str,
    upstream_model: str,
    openai_client: Any,
    google_client: Any,
) -> None:
    if not is_default_conversation_title(current_title):
        return

    title = generate_conversation_title(
        selected_provider=selected_provider,
        upstream_model=upstream_model,
        completion_messages=completion_messages,
        openai_client=openai_client,
        google_client=google_client,
        fallback_title=current_title,
    )
    if not title or title == current_title:
        return

    with open_db_connection(db_file) as conn:
        conn.execute(
            """
            UPDATE conversations
            SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (title[:60], conversation_id),
        )
        conn.commit()
    logger.info("会话标题已自动更新: 会话ID=%s 标题=%s", conversation_id, title)



def _schedule_conversation_title_update(
    *,
    db_file: Path,
    conversation_id: int,
    current_title: str,
    completion_messages: list[dict[str, Any]],
    selected_provider: str,
    upstream_model: str,
    openai_client: Any,
    google_client: Any,
) -> None:
    if not is_default_conversation_title(current_title):
        return

    def runner() -> None:
        try:
            _maybe_update_conversation_title(
                db_file=db_file,
                conversation_id=conversation_id,
                current_title=current_title,
                completion_messages=[dict(item) for item in completion_messages],
                selected_provider=selected_provider,
                upstream_model=upstream_model,
                openai_client=openai_client,
                google_client=google_client,
            )
        except Exception:
            logger.exception("异步更新会话标题失败: 会话ID=%s", conversation_id)

    _TITLE_UPDATE_EXECUTOR.submit(runner)


def _resolve_stream_target(
    conn: Any,
    *,
    conversation_id: int,
    username: str,
    runtime_settings: Any,
    requested_model: str,
    reasoning_effort: str,
    thinking_level: str,
) -> dict[str, Any]:
    conv = conn.execute(
        """
        SELECT id, title, model, reasoning_effort, thinking_level
        FROM conversations
        WHERE id = ? AND username = ?
        """,
        (conversation_id, username),
    ).fetchone()
    if conv is None:
        raise LookupError("会话不存在")

    current_model = normalize_model_selection(
        str(conv["model"]),
        runtime_settings.model_options,
        fallback_to_first=True,
    )
    resolved_model = requested_model or current_model
    model_option = resolve_model_option(resolved_model, runtime_settings.model_options)
    if model_option is None:
        raise ValueError("无效的模型")

    raw_reasoning_effort = reasoning_effort
    raw_thinking_level = thinking_level
    if not raw_reasoning_effort and not raw_thinking_level and model_option.id == current_model:
        raw_reasoning_effort = str(conv["reasoning_effort"] or "").strip().lower()
        raw_thinking_level = str(conv["thinking_level"] or "").strip().lower()

    conversation_settings = resolve_conversation_model_settings(
        model_option,
        reasoning_effort=raw_reasoning_effort,
        thinking_level=raw_thinking_level,
        strict=bool(raw_reasoning_effort or raw_thinking_level),
    )

    return {
        "conversation": conv,
        "conversation_settings": conversation_settings,
        "selected_model_id": model_option.id,
        "selected_provider": model_option.provider,
        "upstream_model": model_option.model_name,
        "effective_openai_reasoning": build_effective_openai_reasoning_settings(
            model_option,
            conversation_settings,
        ),
        "effective_google_thinking": build_effective_google_thinking_settings(
            model_option,
            conversation_settings,
        ),
        "effective_claude_thinking": build_effective_claude_thinking_settings(
            model_option,
            conversation_settings,
        ),
    }


def _load_completion_messages(
    conn: Any,
    *,
    conversation_id: int,
    max_text_file_chars: int,
    max_context_messages: int = 0,
    up_to_message_id: int | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT id, role, content
        FROM messages
        WHERE conversation_id = ?
    """
    params: list[Any] = [conversation_id]
    if isinstance(up_to_message_id, int):
        query += " AND id <= ?"
        params.append(up_to_message_id)
    query += " ORDER BY id DESC"
    if max_context_messages > 0:
        query += " LIMIT ?"
        params.append(max_context_messages)

    rows = list(reversed(conn.execute(query, tuple(params)).fetchall()))
    completion_messages: list[dict[str, Any]] = []
    for row in rows:
        msg_attachments = load_message_attachments(conn, int(row["id"]))
        msg_content = build_message_content_for_model(
            role=str(row["role"]),
            content=str(row["content"]),
            attachments=msg_attachments,
            max_text_file_chars=max_text_file_chars,
        )
        completion_messages.append({"role": str(row["role"]), "content": msg_content})
    return completion_messages


def _stream_chat_response(
    *,
    db_file: Path,
    upload_dir: Path,
    username: str,
    conversation_id: int,
    conversation_title: str,
    completion_messages: list[dict[str, Any]],
    selected_provider: str,
    upstream_model: str,
    effective_openai_reasoning: Any,
    effective_google_thinking: Any,
    effective_claude_thinking: Any,
    runtime_settings: Any,
    openai_client: Any,
    google_client: Any,
    claude_client: Any,
    enable_title_update: bool,
) -> Response:
    def generate() -> Any:
        assistant_parts: list[str] = []
        reasoning_parts: list[str] = []
        has_error = False
        client_disconnected = False
        upstream_finished = False
        delta_count = 0
        usage_input_tokens = 0
        usage_output_tokens = 0
        started_at = time.perf_counter()
        logger.info(
            "开始调用上游模型: 会话ID=%s 来源=%s 模型=%s 上下文消息数=%s",
            conversation_id,
            selected_provider,
            upstream_model,
            len(completion_messages),
        )

        try:
            if selected_provider == PROVIDER_OPENAI:
                if openai_client is None:
                    raise RuntimeError("OpenAI 客户端未初始化，请检查 OPENAI 配置。")
                reasoning_config = _build_openai_reasoning_config(
                    reasoning_settings=effective_openai_reasoning,
                )
                request_kwargs = {
                    "model": upstream_model,
                    "input": build_openai_response_input(completion_messages),
                    "stream": True,
                }
                if reasoning_config is not None:
                    request_kwargs["reasoning"] = reasoning_config
                stream = openai_client.responses.create(**request_kwargs)
                for event_obj in stream:
                    reasoning_delta = extract_reasoning_summary_delta(event_obj)
                    if reasoning_delta:
                        reasoning_parts.append(reasoning_delta)
                        yield sse_payload({"type": "reasoning", "text": reasoning_delta})

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

                    evt_type = getattr(event_obj, "type", "") if not isinstance(event_obj, dict) else event_obj.get("type", "")
                    if evt_type == "response.completed":
                        resp_obj = getattr(event_obj, "response", None)
                        if resp_obj is not None:
                            usage_obj = getattr(resp_obj, "usage", None)
                            if usage_obj is not None:
                                usage_input_tokens = getattr(usage_obj, "input_tokens", 0) or 0
                                usage_output_tokens = getattr(usage_obj, "output_tokens", 0) or 0

                if not assistant_parts and not has_error:
                    has_error = True
                    yield sse_payload(
                        {
                            "type": "error",
                            "error": "请求上游成功但未收到流式文本，请确认网关支持 Responses API 流式。",
                        }
                    )
            elif selected_provider == PROVIDER_GOOGLE:
                if google_client is None:
                    raise RuntimeError("Google Gemini 客户端未初始化，请检查 GOOGLE 配置。")
                request_kwargs = {
                    "model": upstream_model,
                    "contents": build_google_contents(completion_messages),
                }
                google_config = build_google_generate_content_config(
                    thinking_settings=effective_google_thinking,
                )
                if google_config is not None:
                    request_kwargs["config"] = google_config
                stream = google_client.models.generate_content_stream(**request_kwargs)
                for event_obj in stream:
                    reasoning_delta = extract_google_reasoning_delta(event_obj)
                    if reasoning_delta:
                        reasoning_parts.append(reasoning_delta)
                        yield sse_payload({"type": "reasoning", "text": reasoning_delta})

                    delta = extract_google_text_delta(event_obj)
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

                    usage_meta = getattr(event_obj, "usage_metadata", None)
                    if usage_meta is not None:
                        usage_input_tokens = getattr(usage_meta, "prompt_token_count", 0) or 0
                        usage_output_tokens = getattr(usage_meta, "candidates_token_count", 0) or 0

                if not assistant_parts and not has_error:
                    has_error = True
                    yield sse_payload(
                        {
                            "type": "error",
                            "error": "请求 Gemini 成功但未收到流式文本，请确认模型支持流式输出。",
                        }
                    )
            elif selected_provider == PROVIDER_CLAUDE:
                if claude_client is None:
                    raise RuntimeError("Claude 客户端未初始化，请检查 CLAUDE 配置。")
                system_prompt, claude_msgs = build_claude_messages(completion_messages)
                request_kwargs: dict[str, Any] = {
                    "model": upstream_model,
                    "messages": claude_msgs,
                    "max_tokens": 16384,
                }
                if system_prompt:
                    request_kwargs["system"] = system_prompt

                # 注入 Adaptive Thinking 配置
                if effective_claude_thinking is not None and effective_claude_thinking.enabled:
                    thinking_param: dict[str, Any] = {"type": "adaptive"}
                    # display 控制是否返回思考摘要
                    thinking_param["display"] = "summarized" if effective_claude_thinking.include_thoughts else "omitted"
                    request_kwargs["thinking"] = thinking_param
                    if effective_claude_thinking.effort:
                        request_kwargs["output_config"] = {"effort": effective_claude_thinking.effort}

                with claude_client.messages.stream(**request_kwargs) as stream:
                    for event in stream:
                        event_type = getattr(event, "type", "")
                        if event_type == "content_block_delta":
                            delta_obj = getattr(event, "delta", None)
                            if delta_obj is not None:
                                delta_type = getattr(delta_obj, "type", "")
                                if delta_type == "thinking_delta":
                                    thinking_text = getattr(delta_obj, "thinking", "")
                                    if thinking_text:
                                        reasoning_parts.append(thinking_text)
                                        yield sse_payload({"type": "reasoning", "text": thinking_text})
                                elif delta_type == "text_delta":
                                    delta = getattr(delta_obj, "text", "")
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
                        elif event_type == "message_delta":
                            msg_usage = getattr(event, "usage", None)
                            if msg_usage is not None:
                                usage_output_tokens = getattr(msg_usage, "output_tokens", 0) or 0
                        elif event_type == "message_start":
                            msg_obj = getattr(event, "message", None)
                            if msg_obj is not None:
                                msg_usage = getattr(msg_obj, "usage", None)
                                if msg_usage is not None:
                                    usage_input_tokens = getattr(msg_usage, "input_tokens", 0) or 0

                if not assistant_parts and not has_error:
                    has_error = True
                    yield sse_payload(
                        {
                            "type": "error",
                            "error": "请求 Claude 成功但未收到流式文本，请确认模型支持流式输出。",
                        }
                    )
            else:
                raise RuntimeError(f"不支持的模型来源: {selected_provider}")

            logger.info(
                "上游模型调用完成: 会话ID=%s 来源=%s 分片数=%s 输出字符=%s 推理摘要字符=%s 耗时毫秒=%.2f",
                conversation_id,
                selected_provider,
                delta_count,
                len("".join(assistant_parts)),
                len("".join(reasoning_parts)),
                (time.perf_counter() - started_at) * 1000,
            )
            upstream_finished = True

            if usage_input_tokens > 0 or usage_output_tokens > 0:
                yield sse_payload({
                    "type": "usage",
                    "input_tokens": usage_input_tokens,
                    "output_tokens": usage_output_tokens,
                })

        except APIStatusError as exc:
            has_error = True
            friendly, status_code, raw_message = _format_upstream_error(selected_provider, exc)
            logger.warning(
                "上游接口错误: 会话ID=%s 来源=%s 状态=%s 原始信息=%s",
                conversation_id,
                selected_provider,
                status_code if status_code is not None else "unknown",
                raw_message,
            )
            yield sse_payload({"type": "error", "error": friendly})
        except GeneratorExit:
            client_disconnected = True
            logger.info("聊天流连接已断开: 会话ID=%s（客户端可能已关闭连接）", conversation_id)
            raise
        except OpenAIError as exc:
            has_error = True
            logger.exception("OpenAI SDK 调用异常: 会话ID=%s", conversation_id)
            friendly, _, _ = _format_upstream_error(PROVIDER_OPENAI, exc)
            yield sse_payload({"type": "error", "error": friendly})
        except Exception as exc:
            has_error = True
            friendly, status_code, raw_message = _format_upstream_error(selected_provider, exc)
            if exc.__class__.__module__.startswith("anthropic") or exc.__class__.__module__.startswith("google."):
                logger.warning(
                    "上游接口错误: 会话ID=%s 来源=%s 状态=%s 原始信息=%s",
                    conversation_id,
                    selected_provider,
                    status_code if status_code is not None else "unknown",
                    raw_message,
                )
            else:
                logger.exception(
                    "上游 SDK 调用异常: 会话ID=%s 来源=%s 状态=%s 原始信息=%s",
                    conversation_id,
                    selected_provider,
                    status_code if status_code is not None else "unknown",
                    raw_message,
                )
            yield sse_payload({"type": "error", "error": friendly})
        finally:
            assistant_text = "".join(assistant_parts).strip()
            assistant_attachments: list[dict[str, Any]] = []

            if assistant_text or assistant_attachments:
                stored_text = assistant_text
                stored_reasoning = "".join(reasoning_parts).strip()
                stored_status = "complete" if upstream_finished and not has_error else "incomplete"
                _save_assistant_message(
                    db_file=db_file,
                    conversation_id=conversation_id,
                    content=stored_text,
                    reasoning=stored_reasoning,
                    attachments=assistant_attachments,
                    status=stored_status,
                )
                if stored_status == "complete" and enable_title_update:
                    updated_completion_messages = list(completion_messages)
                    updated_completion_messages.append({"role": "assistant", "content": stored_text})
                    _schedule_conversation_title_update(
                        db_file=db_file,
                        conversation_id=conversation_id,
                        current_title=conversation_title,
                        completion_messages=updated_completion_messages,
                        selected_provider=selected_provider,
                        upstream_model=upstream_model,
                        openai_client=openai_client,
                        google_client=google_client,
                    )
                logger.info(
                    "助手消息落库完成: 会话ID=%s 状态=%s 字符数=%s 推理摘要字符=%s 附件数=%s",
                    conversation_id,
                    stored_status,
                    len(stored_text),
                    len(stored_reasoning),
                    len(assistant_attachments),
                )
                if not client_disconnected:
                    if has_error:
                        yield sse_payload({"type": "done", "reply": stored_text, "partial": True})
                    else:
                        yield sse_payload({"type": "done", "reply": stored_text})

                if usage_input_tokens > 0 or usage_output_tokens > 0:
                    try:
                        record_token_usage(
                            db_file,
                            username=username,
                            conversation_id=conversation_id,
                            message_id=None,
                            model=upstream_model,
                            provider=selected_provider,
                            input_tokens=usage_input_tokens,
                            output_tokens=usage_output_tokens,
                        )
                    except Exception:
                        logger.exception("记录 Token 用量失败: 会话ID=%s", conversation_id)
            else:
                if (not has_error) and (not client_disconnected):
                    yield sse_payload({"type": "error", "error": "AI 服务返回空结果"})
                logger.warning(
                    "助手消息为空: 会话ID=%s 是否已有错误=%s",
                    conversation_id,
                    has_error,
                )
                if (not has_error) and (not client_disconnected):
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


def create_chat_blueprint(config: AppConfig) -> Blueprint:
    bp = Blueprint("chat", __name__)

    db_file = config.db_file
    users_file = config.users_file
    upload_dir = config.upload_dir

    @bp.post("/api/chat/stream")
    @require_login
    def chat_stream() -> Response:
        username = _get_current_username()

        runtime_state = get_runtime_state()
        runtime_settings = runtime_state.settings
        openai_client = runtime_state.openai_client
        google_client = runtime_state.google_client
        claude_client = runtime_state.claude_client

        # 检查用户是否有自定义 API Key
        user_record = get_user_record(users_file, username)
        if user_record:
            user_api_keys = user_record.get("api_keys", {})
            if user_api_keys.get("openai"):
                from flask import current_app
                factory = current_app.extensions["openai_client_factory"]
                openai_client = factory(
                    api_key=user_api_keys["openai"],
                    base_url=runtime_settings.openai_base_url,
                )
            if user_api_keys.get("google"):
                from flask import current_app
                factory = current_app.extensions["google_client_factory"]
                google_client = factory(
                    api_key=user_api_keys["google"],
                    base_url=runtime_settings.google_base_url,
                )
            if user_api_keys.get("claude"):
                from flask import current_app
                factory = current_app.extensions["claude_client_factory"]
                claude_client = factory(
                    api_key=user_api_keys["claude"],
                    base_url=runtime_settings.claude_base_url,
                )

        max_upload_mb = runtime_settings.max_upload_mb
        max_upload_bytes = runtime_settings.max_upload_bytes
        max_attachments_per_message = runtime_settings.max_attachments_per_message
        max_text_file_chars = runtime_settings.max_text_file_chars
        allowed_attachment_exts = runtime_settings.allowed_attachment_exts

        content_type = request.content_type or ""
        uploaded_files: list[FileStorage] = []
        content = ""
        model = ""
        reasoning_effort = ""
        thinking_level = ""
        conversation_id: int | None = None

        if content_type.startswith("multipart/form-data"):
            content = str(request.form.get("content", "")).strip()
            model = str(request.form.get("model", "")).strip()
            reasoning_effort = str(request.form.get("reasoning_effort", "")).strip().lower()
            thinking_level = str(request.form.get("thinking_level", "")).strip().lower()
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
            reasoning_effort = str(payload.get("reasoning_effort", "")).strip().lower()
            thinking_level = str(payload.get("thinking_level", "")).strip().lower()
            conversation_id = payload.get("conversation_id")
            if not isinstance(conversation_id, int):
                conversation_id = safe_int(conversation_id)

        logger.info(
            "聊天流请求: 用户=%s 会话ID=%s 模型=%s effort=%s level=%s 文本长度=%s 附件数量=%s 请求类型=%s",
            username,
            conversation_id,
            model,
            reasoning_effort,
            thinking_level,
            len(content),
            len(uploaded_files),
            content_type,
        )

        log_audit(
            db_file,
            username=username,
            action="chat",
            target_type="conversation",
            target_id=str(conversation_id or "new"),
            detail=f"model={model} files={len(uploaded_files)}",
            ip_address=request.remote_addr or "",
        )

        if not content and not uploaded_files:
            return jsonify({"ok": False, "error": "消息内容和附件不能同时为空"}), 400

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

            parsed_text = ""
            kind = "binary"
            content_part: dict[str, Any]

            if is_image_attachment(file_name, mime_type):
                kind = "image"
                content_part = {
                    "type": "image_url",
                    "image_url": {"url": to_data_url(raw, mime_type)},
                }
            else:
                parsed_text = _parse_file_to_markdown(file_name, mime_type, raw)
                if parsed_text:
                    kind = "text"
                    content_part = {"type": "text", "text": f"[文件: {file_name}]\n{parsed_text}\n[文件结束]"}
                else:
                    kind = "binary"
                    content_part = {"type": "text", "text": f"[无法解析的文件: {file_name}]"}

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
        with open_db_connection(db_file) as conn:
            try:
                stream_target = _resolve_stream_target(
                    conn,
                    conversation_id=conversation_id,
                    username=username,
                    runtime_settings=runtime_settings,
                    requested_model=model,
                    reasoning_effort=reasoning_effort,
                    thinking_level=thinking_level,
                )
            except LookupError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 404
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400

            conv = stream_target["conversation"]
            conversation_settings = stream_target["conversation_settings"]
            completion_messages = _load_completion_messages(
                conn,
                conversation_id=conversation_id,
                max_text_file_chars=max_text_file_chars,
                max_context_messages=runtime_settings.max_context_messages,
            )
            count_row = conn.execute(
                "SELECT COUNT(1) AS total FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            existing_count = count_row["total"] if count_row else 0
            logger.info(
                "历史消息加载完成: 会话ID=%s 历史消息数=%s 本次附件数=%s",
                conversation_id,
                len(completion_messages),
                len(prepared_attachments),
            )

            cursor = conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, status)
                VALUES (?, 'user', ?, 'complete')
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

            conn.execute(
                """
                UPDATE conversations
                SET model = ?, reasoning_effort = ?, thinking_level = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    stream_target["selected_model_id"],
                    conversation_settings.reasoning_effort,
                    conversation_settings.thinking_level,
                    conversation_id,
                ),
            )
            conn.commit()
            logger.info(
                "用户消息落库完成: 会话ID=%s 用户消息ID=%s",
                conversation_id,
                user_message_id,
            )

        return _stream_chat_response(
            db_file=db_file,
            upload_dir=upload_dir,
            username=username,
            conversation_id=conversation_id,
            conversation_title=str(conv["title"]),
            completion_messages=completion_messages,
            selected_provider=stream_target["selected_provider"],
            upstream_model=stream_target["upstream_model"],
            effective_openai_reasoning=stream_target["effective_openai_reasoning"],
            effective_google_thinking=stream_target["effective_google_thinking"],
            effective_claude_thinking=stream_target["effective_claude_thinking"],
            runtime_settings=runtime_settings,
            openai_client=openai_client,
            google_client=google_client,
            claude_client=claude_client,
            enable_title_update=(existing_count == 0),
        )

    @bp.post("/api/chat/retry/stream")
    @require_login
    def retry_chat_stream() -> Response:
        username = _get_current_username()

        content_type = request.content_type or ""
        conversation_id: int | None
        if content_type.startswith("multipart/form-data"):
            conversation_id = safe_int(request.form.get("conversation_id"))
        else:
            payload = request.get_json(silent=True) or {}
            conversation_id = payload.get("conversation_id")
            if not isinstance(conversation_id, int):
                conversation_id = safe_int(conversation_id)

        if not isinstance(conversation_id, int):
            return jsonify({"ok": False, "error": "conversation_id 无效"}), 400

        runtime_state = get_runtime_state()
        runtime_settings = runtime_state.settings
        openai_client = runtime_state.openai_client
        google_client = runtime_state.google_client
        claude_client = runtime_state.claude_client

        # 检查用户是否有自定义 API Key
        user_record = get_user_record(users_file, username)
        if user_record:
            user_api_keys = user_record.get("api_keys", {})
            if user_api_keys.get("openai"):
                from flask import current_app
                factory = current_app.extensions["openai_client_factory"]
                openai_client = factory(
                    api_key=user_api_keys["openai"],
                    base_url=runtime_settings.openai_base_url,
                )
            if user_api_keys.get("google"):
                from flask import current_app
                factory = current_app.extensions["google_client_factory"]
                google_client = factory(
                    api_key=user_api_keys["google"],
                    base_url=runtime_settings.google_base_url,
                )
            if user_api_keys.get("claude"):
                from flask import current_app
                factory = current_app.extensions["claude_client_factory"]
                claude_client = factory(
                    api_key=user_api_keys["claude"],
                    base_url=runtime_settings.claude_base_url,
                )

        max_text_file_chars = runtime_settings.max_text_file_chars
        logger.info("聊天重试请求: 用户=%s 会话ID=%s", username, conversation_id)

        with open_db_connection(db_file) as conn:
            try:
                stream_target = _resolve_stream_target(
                    conn,
                    conversation_id=conversation_id,
                    username=username,
                    runtime_settings=runtime_settings,
                    requested_model="",
                    reasoning_effort="",
                    thinking_level="",
                )
            except LookupError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 404
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400

            tail_rows = conn.execute(
                """
                SELECT id, role, status
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT 2
                """,
                (conversation_id,),
            ).fetchall()
            if not tail_rows:
                return jsonify({"ok": False, "error": "当前会话没有可重试的消息"}), 400

            last_row = tail_rows[0]
            retry_user_message_id: int | None = None
            stale_assistant_message_id: int | None = None
            last_role = str(last_row["role"])
            last_status = str(last_row["status"] or "complete")

            if last_role == "user":
                retry_user_message_id = int(last_row["id"])
            elif last_role == "assistant" and last_status == "incomplete":
                if len(tail_rows) < 2 or str(tail_rows[1]["role"]) != "user":
                    return jsonify({"ok": False, "error": "最后一条消息状态异常，无法重试"}), 400
                stale_assistant_message_id = int(last_row["id"])
                retry_user_message_id = int(tail_rows[1]["id"])
            else:
                return jsonify({"ok": False, "error": "当前没有可重试的失败回复"}), 400

            completion_messages = _load_completion_messages(
                conn,
                conversation_id=conversation_id,
                max_text_file_chars=max_text_file_chars,
                max_context_messages=runtime_settings.max_context_messages,
                up_to_message_id=retry_user_message_id,
            )
            logger.info(
                "重试历史消息加载完成: 会话ID=%s 上下文消息数=%s",
                conversation_id,
                len(completion_messages),
            )

            if stale_assistant_message_id is not None:
                conn.execute(
                    "DELETE FROM message_attachments WHERE message_id = ?",
                    (stale_assistant_message_id,),
                )
                conn.execute(
                    "DELETE FROM messages WHERE id = ?",
                    (stale_assistant_message_id,),
                )
                logger.info(
                    "已清理未完成助手消息: 会话ID=%s 助手消息ID=%s",
                    conversation_id,
                    stale_assistant_message_id,
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

        return _stream_chat_response(
            db_file=db_file,
            upload_dir=upload_dir,
            username=username,
            conversation_id=conversation_id,
            conversation_title=str(stream_target["conversation"]["title"]),
            completion_messages=completion_messages,
            selected_provider=stream_target["selected_provider"],
            upstream_model=stream_target["upstream_model"],
            effective_openai_reasoning=stream_target["effective_openai_reasoning"],
            effective_google_thinking=stream_target["effective_google_thinking"],
            effective_claude_thinking=stream_target["effective_claude_thinking"],
            runtime_settings=runtime_settings,
            openai_client=openai_client,
            google_client=google_client,
            claude_client=claude_client,
            enable_title_update=False,
        )

    return bp
