from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from mimetypes import guess_extension
from pathlib import Path
from typing import Any
from urllib.request import urlopen
from uuid import uuid4

from gtpweb.ai_providers import PROVIDER_GOOGLE, PROVIDER_OPENAI
from gtpweb.attachments import infer_mime_type

logger = logging.getLogger(__name__)

_OPENAI_SIZE_TO_GOOGLE_ASPECT_RATIO = {
    "1024x1024": "1:1",
    "1024x1792": "9:16",
    "1792x1024": "16:9",
}


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


@dataclass(frozen=True)
class ImageToolSelection:
    provider: str
    model_name: str



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



def _build_generated_file_name(mime_type: str) -> str:
    normalized = str(mime_type or "").strip() or "image/png"
    ext = guess_extension(normalized) or ".png"
    if ext == ".jpe":
        ext = ".jpg"
    return f"generated{ext}"



def _read_google_generated_image(item: Any) -> tuple[bytes, str, str] | None:
    image = item.get("image") if isinstance(item, dict) else getattr(item, "image", None)
    if image is None:
        reason = item.get("rai_filtered_reason") if isinstance(item, dict) else getattr(item, "rai_filtered_reason", None)
        if isinstance(reason, str) and reason.strip():
            raise RuntimeError(f"图片生成被安全策略拦截：{reason.strip()}")
        return None

    if isinstance(image, dict):
        image_bytes = image.get("image_bytes")
        mime_type = image.get("mime_type")
        gcs_uri = image.get("gcs_uri")
    else:
        image_bytes = getattr(image, "image_bytes", None)
        mime_type = getattr(image, "mime_type", None)
        gcs_uri = getattr(image, "gcs_uri", None)

    normalized_mime_type = str(mime_type or "").strip() or "image/png"
    if isinstance(image_bytes, bytes) and image_bytes:
        return image_bytes, _build_generated_file_name(normalized_mime_type), normalized_mime_type

    if isinstance(gcs_uri, str) and gcs_uri.strip():
        if gcs_uri.startswith(("http://", "https://")):
            with urlopen(gcs_uri, timeout=30) as response:
                response_mime_type = response.headers.get_content_type() or normalized_mime_type
                file_name = Path(response.url).name or _build_generated_file_name(response_mime_type)
                return response.read(), file_name, response_mime_type
        raise RuntimeError("Google 图片接口返回了暂不支持直接下载的远程地址。")

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



def _build_success_result(
    *,
    image_result: tuple[bytes, str, str],
    conversation_id: int,
    upload_dir: Path,
    safe_username: str,
) -> ActionExecutionResult:
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



def _resolve_image_tool_selection(
    *,
    image_tool_provider: str,
    openai_image_model: str,
    google_image_model: str,
) -> ImageToolSelection | None:
    provider = str(image_tool_provider or "").strip().lower() or PROVIDER_OPENAI
    if provider == PROVIDER_GOOGLE:
        model_name = str(google_image_model or "").strip()
        return ImageToolSelection(provider=provider, model_name=model_name) if model_name else None

    model_name = str(openai_image_model or "").strip()
    return ImageToolSelection(provider=PROVIDER_OPENAI, model_name=model_name) if model_name else None



def _build_google_image_config(action: AssistantAction) -> dict[str, Any]:
    config: dict[str, Any] = {}
    negative_prompt = str(action.action_input.get("negative_prompt", "")).strip()
    aspect_ratio = str(action.action_input.get("aspect_ratio", "")).strip()
    size = str(action.action_input.get("size", "")).strip()
    output_mime_type = str(action.action_input.get("output_mime_type", "")).strip()
    image_size = str(action.action_input.get("image_size", "")).strip()

    if negative_prompt:
        config["negative_prompt"] = negative_prompt
    if not aspect_ratio and size:
        aspect_ratio = _OPENAI_SIZE_TO_GOOGLE_ASPECT_RATIO.get(size, "")
    if aspect_ratio:
        config["aspect_ratio"] = aspect_ratio
    if output_mime_type:
        config["output_mime_type"] = output_mime_type
    if image_size:
        config["image_size"] = image_size
    return config



def _execute_openai_image_action(
    action: AssistantAction,
    *,
    model_name: str,
    openai_client: Any | None,
    prompt: str,
    conversation_id: int,
    upload_dir: Path,
    safe_username: str,
) -> ActionExecutionResult:
    if openai_client is None:
        return ActionExecutionResult(
            message_text="模型请求生成图片，但当前系统未配置可用的图片生成服务。"
        )

    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "prompt": prompt,
    }
    size = str(action.action_input.get("size", "")).strip()
    quality = str(action.action_input.get("quality", "")).strip()
    if size:
        request_kwargs["size"] = size
    if quality:
        request_kwargs["quality"] = quality

    logger.info(
        "开始执行图片动作: 动作=%s 会话ID=%s Provider=%s 模型=%s 提示词长度=%s",
        action.name,
        conversation_id,
        PROVIDER_OPENAI,
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

    return _build_success_result(
        image_result=image_result,
        conversation_id=conversation_id,
        upload_dir=upload_dir,
        safe_username=safe_username,
    )



def _execute_google_image_action(
    action: AssistantAction,
    *,
    model_name: str,
    google_client: Any | None,
    prompt: str,
    conversation_id: int,
    upload_dir: Path,
    safe_username: str,
) -> ActionExecutionResult:
    if google_client is None:
        return ActionExecutionResult(
            message_text="模型请求生成图片，但当前系统未配置可用的图片生成服务。"
        )

    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "prompt": prompt,
    }
    config = _build_google_image_config(action)
    if config:
        request_kwargs["config"] = config

    logger.info(
        "开始执行图片动作: 动作=%s 会话ID=%s Provider=%s 模型=%s 提示词长度=%s",
        action.name,
        conversation_id,
        PROVIDER_GOOGLE,
        model_name,
        len(prompt),
    )
    response = google_client.models.generate_images(**request_kwargs)
    generated_images = getattr(response, "generated_images", None)
    if not isinstance(generated_images, list) or not generated_images:
        raise RuntimeError("图片接口返回空结果")

    image_result = _read_google_generated_image(generated_images[0])
    if image_result is None:
        raise RuntimeError("图片接口未返回可识别的图片内容")

    return _build_success_result(
        image_result=image_result,
        conversation_id=conversation_id,
        upload_dir=upload_dir,
        safe_username=safe_username,
    )



def execute_assistant_action(
    action: AssistantAction,
    *,
    image_tool_provider: str,
    openai_image_model: str,
    google_image_model: str,
    openai_client: Any | None,
    google_client: Any | None,
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

    image_tool_selection = _resolve_image_tool_selection(
        image_tool_provider=image_tool_provider,
        openai_image_model=openai_image_model,
        google_image_model=google_image_model,
    )
    if image_tool_selection is None:
        return ActionExecutionResult(message_text="模型请求生成图片，但当前系统未启用该能力。")

    try:
        if image_tool_selection.provider == PROVIDER_GOOGLE:
            return _execute_google_image_action(
                action,
                model_name=image_tool_selection.model_name,
                google_client=google_client,
                prompt=prompt,
                conversation_id=conversation_id,
                upload_dir=upload_dir,
                safe_username=safe_username,
            )
        return _execute_openai_image_action(
            action,
            model_name=image_tool_selection.model_name,
            openai_client=openai_client,
            prompt=prompt,
            conversation_id=conversation_id,
            upload_dir=upload_dir,
            safe_username=safe_username,
        )
    except Exception as exc:
        logger.warning(
            "图片动作执行失败: 动作=%s 会话ID=%s Provider=%s 模型=%s 错误=%s",
            action.name,
            conversation_id,
            image_tool_selection.provider,
            image_tool_selection.model_name,
            exc,
        )
        return ActionExecutionResult(message_text=f"模型请求生成图片，但执行失败：{exc}")
