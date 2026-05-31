from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any, Iterable

from openai import APIStatusError

from gtpweb.utils import model_name_matches_patterns


def sse_payload(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def get_obj_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    model_dump = getattr(obj, "model_dump", None)
    if callable(model_dump):
        try:
            data = model_dump()
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
    return {}


def extract_text_delta(event_obj: Any) -> str:
    event_type = get_obj_value(event_obj, "type")
    if event_type == "response.output_text.delta":
        delta = get_obj_value(event_obj, "delta")
        return delta if isinstance(delta, str) else ""

    event_dict = to_dict(event_obj)
    if not event_dict:
        return ""

    choices = event_dict.get("choices")
    if isinstance(choices, list) and choices:
        delta_obj = choices[0].get("delta", {})
        if isinstance(delta_obj, dict):
            content = delta_obj.get("content")
            if isinstance(content, str):
                return content
    return ""


def extract_reasoning_summary_delta(event_obj: Any) -> str:
    event_type = get_obj_value(event_obj, "type")
    if event_type == "response.reasoning_summary_text.delta":
        delta = get_obj_value(event_obj, "delta")
        return delta if isinstance(delta, str) else ""
    return ""


def supports_openai_reasoning(model_name: str, model_patterns: Iterable[str]) -> bool:
    return model_name_matches_patterns(model_name, model_patterns)


logger = logging.getLogger(__name__)


class FileUploadError(RuntimeError):
    pass


def _upload_to_openai_files(openai_client: Any, file_name: str, raw: bytes, mime_type: str) -> str:
    """上传文件到 OpenAI Files API，返回 file_id。失败抛出 FileUploadError。"""
    try:
        result = openai_client.files.create(
            file=(file_name, raw, mime_type),
            purpose="responses",
        )
        logger.info("OpenAI 文件上传成功: 文件=%s file_id=%s 大小=%s", file_name, result.id, len(raw))
        return result.id
    except Exception as exc:
        raise FileUploadError(f"文件 {file_name} 上传到 OpenAI 失败: {exc}") from exc


def _build_response_input_content(
    content: Any,
    openai_client: Any = None,
) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    converted: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type", "")).strip().lower()
        if item_type == "text":
            text = item.get("text")
            if isinstance(text, str) and text:
                converted.append({"type": "input_text", "text": text})
            continue
        if item_type == "image_url":
            image_url = item.get("image_url")
            if not isinstance(image_url, dict):
                continue
            url = image_url.get("url")
            if not isinstance(url, str) or not url:
                continue
            if openai_client and url.startswith("data:"):
                match = _DATA_URL_RE.match(url)
                if match:
                    raw = base64.b64decode(match.group("data"))
                    mime = match.group("mime")
                    fid = _upload_to_openai_files(openai_client, "image.png", raw, mime)
                    converted.append({"type": "input_image", "file_id": fid, "detail": "auto"})
                    continue
            converted.append({"type": "input_image", "image_url": url, "detail": "auto"})
            continue
        if item_type == "file":
            file_data_b64 = item.get("data", "")
            file_mime = str(item.get("mime_type", "application/octet-stream"))
            file_name = str(item.get("file_name", "file"))
            if not file_data_b64:
                continue
            raw = base64.b64decode(file_data_b64)
            if openai_client:
                fid = _upload_to_openai_files(openai_client, file_name, raw, file_mime)
                converted.append({"type": "input_file", "file_id": fid, "filename": file_name})
            else:
                converted.append({
                    "type": "input_file",
                    "filename": file_name,
                    "file_data": f"data:{file_mime};base64,{file_data_b64}",
                })

    return converted if converted else ""


_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.DOTALL)


def build_openai_response_input(
    messages: list[dict[str, Any]],
    openai_client: Any = None,
) -> list[dict[str, Any]]:
    response_input: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", "user")).strip().lower() or "user"
        if role not in {"user", "assistant", "system", "developer"}:
            continue
        content = _build_response_input_content(message.get("content"), openai_client=openai_client)
        if content == "":
            continue

        item: dict[str, Any] = {
            "type": "message",
            "role": role,
            "content": content,
        }
        if role == "assistant":
            item["phase"] = "final_answer"
        response_input.append(item)
    return response_input


def extract_error_message(data: dict[str, Any], fallback: str = "AI 服务返回错误") -> str:
    error_obj = data.get("error")
    if isinstance(error_obj, dict):
        message = error_obj.get("message")
        if isinstance(message, str) and message:
            return message
    return fallback


def summarize_non_json_error(body_text: str) -> str:
    raw = body_text.strip()
    if not raw:
        return "上游返回空响应"

    lowered = raw.lower()
    if "<html" in lowered:
        match = re.search(r"<title>(.*?)</title>", raw, flags=re.IGNORECASE | re.DOTALL)
        if match:
            title = " ".join(match.group(1).split())[:120]
            return f"上游返回 HTML 页面: {title}"
        return "上游返回 HTML 页面，通常是 OPENAI_BASE_URL 配置错误或被网关拦截。"

    return raw[:300]


def extract_status_error_message(exc: APIStatusError, fallback: str = "AI 服务返回错误") -> tuple[int | None, str]:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if response is None:
        return status_code, str(exc) or fallback

    try:
        data = response.json()
        if isinstance(data, dict):
            return response.status_code, extract_error_message(data, fallback=fallback)
    except Exception:
        pass

    body_text = ""
    try:
        body_text = response.text
    except Exception:
        body_text = ""

    if body_text:
        return response.status_code, summarize_non_json_error(body_text)
    return response.status_code, str(exc) or fallback
