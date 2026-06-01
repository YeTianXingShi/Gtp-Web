"""
SPA 启动数据蓝图

提供前端 SPA 启动时一次拉齐所需的元数据：
- GET /api/bootstrap：当前用户、可用模型、附件限制等（取代旧 chat.html 的 window.__APP_CONFIG__）
- GET /api/tutorial ：教程 markdown 原文（前端自行渲染）
"""

from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from flask import Blueprint, jsonify, send_file

from gtpweb.ai_providers import build_model_groups, serialize_model_options
from gtpweb.auth_jwt import require_login
from gtpweb.config import AppConfig
from gtpweb.runtime_state import get_runtime_state
from gtpweb.user_store import get_user_record

logger = logging.getLogger(__name__)


def _serialize_group(group: Any) -> dict[str, Any]:
    return {
        "key": group.key,
        "label": group.label,
        "options": [
            {
                "id": option.id,
                "label": option.label,
                "provider": option.provider,
                "model_name": option.model_name,
            }
            for option in group.options
        ],
    }


def _serialize_model_option(option: dict[str, Any]) -> dict[str, Any]:
    """把 serialize_model_options 返回的项中的 dataclass 字段转为 dict。"""
    result: dict[str, Any] = {}
    for key, value in option.items():
        if is_dataclass(value) and not isinstance(value, type):
            result[key] = asdict(value)
        else:
            result[key] = value
    return result


def create_bootstrap_blueprint(config: AppConfig) -> Blueprint:
    bp = Blueprint("bootstrap", __name__)

    tutorial_file = config.db_file.parent / "tutorial.md"

    @bp.get("/api/bootstrap")
    @require_login
    def bootstrap() -> Any:
        """返回 SPA 启动所需的元数据。"""
        from flask import g
        runtime_settings = get_runtime_state().settings

        groups = build_model_groups(runtime_settings.model_options)
        options_raw = serialize_model_options(runtime_settings.model_options)

        return jsonify(
            {
                "ok": True,
                "user": {
                    "username": g.user["username"],
                    "is_admin": bool(g.user["is_admin"]),
                },
                "models": {
                    "groups": [_serialize_group(group) for group in groups],
                    "options": [_serialize_model_option(option) for option in options_raw],
                    "default": runtime_settings.models[0] if runtime_settings.models else "",
                },
                "attachments": {
                    "max_per_message": runtime_settings.max_attachments_per_message,
                    "max_upload_mb": runtime_settings.max_upload_mb,
                    "allowed_exts": sorted(runtime_settings.allowed_attachment_exts),
                },
            }
        )

    @bp.get("/api/tutorial")
    @require_login
    def tutorial() -> Any:
        """返回教程 markdown 原文，由前端渲染。"""
        if not tutorial_file.exists():
            return jsonify({"ok": True, "content": "", "exists": False})
        content = tutorial_file.read_text(encoding="utf-8")
        return jsonify({"ok": True, "content": content, "exists": True})

    @bp.get("/api/clients-config")
    @require_login
    def clients_config() -> Any:
        """返回外部客户端（Codex / Claude Code）所需的 base_url 与当前用户的 api_key。

        - openai 用于 Codex CLI / Codex 桌面客户端（OpenAI 兼容接口）
        - claude 用于 Claude Code（Anthropic 兼容接口）
        - 若用户未配置自己的 api_key，返回空串，由前端提示使用全局 key 或联系管理员
        """
        from flask import g

        runtime_settings = get_runtime_state().settings
        username = g.user["username"]
        record = get_user_record(config.users_file, username) or {}
        user_api_keys = record.get("api_keys", {}) or {}

        return jsonify(
            {
                "ok": True,
                "openai": {
                    "base_url": runtime_settings.openai_base_url,
                    "api_key": user_api_keys.get("openai", ""),
                },
                "claude": {
                    "base_url": runtime_settings.claude_base_url,
                    "api_key": user_api_keys.get("claude", ""),
                },
            }
        )

    @bp.get("/api/logo")
    def serve_logo() -> Any:
        """提供自定义 logo（无需登录）。优先使用 data/ 下的自定义 logo，否则回退到前端默认 logo。"""
        from pathlib import Path
        custom_logo = Path(config.db_file).parent / "logo.png"
        if custom_logo.is_file():
            return send_file(custom_logo, mimetype="image/png")
        default_logo = Path(__file__).parent.parent.parent / "static" / "dist" / "logo.png"
        if default_logo.is_file():
            return send_file(default_logo, mimetype="image/png")
        return "", 404

    return bp
