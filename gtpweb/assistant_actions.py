from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlopen
from uuid import uuid4

from gtpweb.attachments import infer_mime_type

logger = logging.getLogger(__name__)

DEFAULT_IMAGE_TOOL_MODEL_CANDIDATES = (
    "dall-e-3",
    "gpt-image-1",
)


@dataclass(frozen=True)
class AssistantAction:
    name: str
    action_input: dict[str, Any]
    thought: str
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class ActionExecutionResult:
    message_text: str
    attachments: tuple[dict[str, Any], ...] = ()



def _normalize_json_object(raw_value: Any) -> dict[str, Any] | None:
    if isinstance(raw_value, dict):
        return raw_value
    if not isinstance(raw_value, str):
        return None

    text = raw_value.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data



def _strip_json_code_fence(raw_text: str) -> str:
    text = raw_text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def parse_assistant_action(text: str) -> AssistantAction | None:
    raw_text = _strip_json_code_fence(str(text or "").strip())
    if not raw_text.startswith("{") or not raw_text.endswith("}"):
        return None

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    action_name = str(payload.get("action", "")).strip()
    if not action_name:
        return None

    action_input = _normalize_json_object(payload.get("action_input"))
    if action_input is None:
        return None

    thought = str(payload.get("thought", "")).strip()
    return AssistantAction(
        name=action_name,
        action_input=action_input,
        thought=thought,
        raw_payload=payload,
    )



def _read_image_response_item(item: Any) -> tuple[bytes, str, str] | None:
    if isinstance(item, dict):
        b64_json = item.get("b64_json")
        url = item.get("url")
    else:
        b64_json = getattr(item, "b64_json", None)
        url = getattr(item, "url", None)
    if isinstance(b64_json, str) and b64_json.strip():
        return base64.b64decode(b64_json), "generated.png", "image/png"

    if isinstance(url, str) and url.strip():
        with urlopen(url, timeout=30) as response:
            mime_type = response.headers.get_content_type() or "application/octet-stream"
            file_name = Path(response.url).name or f"generated_{uuid4().hex[:8]}"
            if "." not in file_name:
                suffix = Path(url).suffix or Path(file_name).suffix
                file_name = f"{file_name}{suffix}"
            return response.read(), file_name, mime_type

    return None



def _save_generated_image(
    *,
    image_bytes: bytes,
    file_name: str,
    mime_type: str,
    conversation_id: int,
    upload_dir: Path,
    safe_username: str,
) -> dict[str, Any]:
    ext = Path(file_name).suffix or Path(f"generated{Path(file_name).suffix}").suffix
    if not ext:
        ext = Path(file_name).suffix or ".png"
    final_name = file_name if Path(file_name).suffix else f"generated_image{ext}"

    target_dir = upload_dir / safe_username / str(conversation_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    saved_name = f"{uuid4().hex}_{final_name}"
    saved_path = target_dir / saved_name
    saved_path.write_bytes(image_bytes)

    return {
        "file_name": final_name,
        "file_path": str(saved_path),
        "mime_type": mime_type or infer_mime_type(final_name),
        "kind": "image",
        "parsed_text": "",
    }



def _build_image_generation_candidates(action: AssistantAction) -> list[str]:
    candidates: list[str] = []
    requested_model = str(action.action_input.get("model", "")).strip()
    if requested_model:
        candidates.append(requested_model)
    for model_name in DEFAULT_IMAGE_TOOL_MODEL_CANDIDATES:
        if model_name not in candidates:
            candidates.append(model_name)
    return candidates



def execute_assistant_action(
    action: AssistantAction,
    *,
    openai_client: Any | None,
    conversation_id: int,
    upload_dir: Path,
    safe_username: str,
) -> ActionExecutionResult:
    logger.info(
        "检测到助手动作: 名称=%s 会话ID=%s 思考长度=%s",
        action.name,
        conversation_id,
        len(action.thought),
    )

    if action.name != "dalle.text2im":
        return ActionExecutionResult(
            message_text=f"模型请求调用工具 `{action.name}`，但当前系统暂不支持该动作。"
        )

    prompt = str(action.action_input.get("prompt", "")).strip()
    if not prompt:
        return ActionExecutionResult(message_text="模型请求生成图片，但未提供有效的图片提示词。")

    if openai_client is None:
        return ActionExecutionResult(
            message_text="模型请求生成图片，但当前系统未配置可用的图片生成服务。"
        )

    last_error: Exception | None = None
    size = str(action.action_input.get("size", "")).strip()
    quality = str(action.action_input.get("quality", "")).strip()

    for model_name in _build_image_generation_candidates(action):
        try:
            request_kwargs: dict[str, Any] = {
                "model": model_name,
                "prompt": prompt,
            }
            if size:
                request_kwargs["size"] = size
            if quality:
                request_kwargs["quality"] = quality

            logger.info(
                "开始执行图片动作: 动作=%s 会话ID=%s 模型=%s 提示词长度=%s",
                action.name,
                conversation_id,
                model_name,
                len(prompt),
            )
            response = openai_client.images.generate(**request_kwargs)
            data = getattr(response, "data", None)
            if not isinstance(data, list) or not data:
                raise RuntimeError("图片接口返回空结果")

            image_result = _read_image_response_item(data[0])
            if image_result is None:
                raise RuntimeError("图片接口未返回可识别的图片内容")

            image_bytes, file_name, mime_type = image_result
            attachment = _save_generated_image(
                image_bytes=image_bytes,
                file_name=file_name,
                mime_type=mime_type,
                conversation_id=conversation_id,
                upload_dir=upload_dir,
                safe_username=safe_username,
            )
            return ActionExecutionResult(
                message_text="已为你生成图片，请查看下方结果。",
                attachments=(attachment,),
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "图片动作执行失败，将尝试下一个模型: 动作=%s 会话ID=%s 模型=%s 错误=%s",
                action.name,
                conversation_id,
                model_name,
                exc,
            )

    error_message = str(last_error) if last_error is not None else "未知错误"
    return ActionExecutionResult(message_text=f"模型请求生成图片，但执行失败：{error_message}")
