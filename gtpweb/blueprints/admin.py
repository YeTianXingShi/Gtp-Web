"""
管理员蓝图模块

本模块处理管理员相关的路由和功能，包括：
- 管理员页面
- 配置文件管理（用户配置、模型配置、环境变量）
- 配置文件编辑和保存
- 热更新配置
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from gtpweb.config import AppConfig, ENV_GROUP_SPECS, parse_model_catalog_text
from gtpweb.runtime_state import apply_runtime_config_values, read_env_files_values
from gtpweb.user_store import get_user_record, normalize_users_config, save_users_config, users_config_to_text

logger = logging.getLogger(__name__)


CONFIG_FILE_AUTH_USERS = "auth_users"
CONFIG_FILE_MODELS = "models"


def _get_current_user_record(users_file: Path) -> dict[str, Any] | None:
    username = session.get("username")
    if not isinstance(username, str) or not username:
        return None

    record = get_user_record(users_file, username)
    if record is None:
        logger.warning("后台访问用户不存在，已清理登录态: 用户名=%s", username)
        session.clear()
        return None
    return record


def _require_admin_page(users_file: Path) -> dict[str, Any] | None:
    record = _get_current_user_record(users_file)
    if record is None:
        return None
    if not record["is_admin"]:
        return None
    return record


def _require_admin_api(users_file: Path) -> tuple[dict[str, Any] | None, tuple[Any, int] | None]:
    record = _get_current_user_record(users_file)
    if record is None:
        return None, (jsonify({"ok": False, "error": "请先登录"}), 401)
    if not record["is_admin"]:
        return None, (jsonify({"ok": False, "error": "需要管理员权限"}), 403)
    return record, None


def _normalize_text_file_content(raw_text: str) -> str:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def _build_config_file_items(config: AppConfig) -> dict[str, dict[str, Any]]:
    config_files: dict[str, dict[str, Any]] = {
        CONFIG_FILE_AUTH_USERS: {
            "id": CONFIG_FILE_AUTH_USERS,
            "label": "认证配置",
            "description": "直接编辑用户认证 JSON，保存后立即生效。",
            "path": config.users_file,
            "requires_restart": False,
            "format": "json",
        },
        CONFIG_FILE_MODELS: {
            "id": CONFIG_FILE_MODELS,
            "label": "模型配置",
            "description": "按模型维护 OpenAI / Google 的可用模型、图片模型与 reasoning / thinking 参数，支持 JSON 注释，保存后立即热更新。",
            "path": config.model_config_file,
            "requires_restart": False,
            "format": "jsonc",
        },
    }
    for spec, path in zip(ENV_GROUP_SPECS, config.env_files):
        config_files[f"env_{spec.key}"] = {
            "id": f"env_{spec.key}",
            "label": spec.label,
            "description": f"{spec.description} 保存后会自动热更新支持的运行项，结构性配置仍需重启。",
            "path": path,
            "requires_restart": True,
            "format": "dotenv",
        }
    return config_files


def _serialize_config_file_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "label": item["label"],
        "description": item["description"],
        "path": str(item["path"]),
        "requires_restart": bool(item["requires_restart"]),
        "format": item["format"],
    }


def _get_config_file_item(config_files: dict[str, dict[str, Any]], file_id: str) -> dict[str, Any]:
    item = config_files.get(file_id)
    if item is None:
        raise ValueError("不支持的配置文件")
    return item


def _read_config_file_content(item: dict[str, Any]) -> str:
    path = Path(item["path"])
    if item["id"] == CONFIG_FILE_AUTH_USERS:
        if not path.exists():
            return users_config_to_text({"users": []})
        normalized = normalize_users_config(json.loads(path.read_text(encoding="utf-8")))
        return users_config_to_text(normalized)
    if item["id"] == CONFIG_FILE_MODELS:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _save_config_file_content(
    item: dict[str, Any],
    raw_content: str,
    *,
    current_username: str,
) -> str:
    path = Path(item["path"])
    if item["id"] == CONFIG_FILE_AUTH_USERS:
        try:
            raw_data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 解析失败: 第 {exc.lineno} 行第 {exc.colno} 列 {exc.msg}") from exc

        normalized = normalize_users_config(raw_data, require_admin=True)
        current_user_still_admin = next(
            (
                user
                for user in normalized["users"]
                if user["username"] == current_username and user["is_admin"]
            ),
            None,
        )
        if current_user_still_admin is None:
            raise ValueError("保存后当前登录管理员必须仍然存在且保留管理员权限")

        save_users_config(path, normalized, require_admin=True)
        return users_config_to_text(normalized)

    if item["id"] == CONFIG_FILE_MODELS:
        parse_model_catalog_text(raw_content)
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized_text = _normalize_text_file_content(raw_content)
        path.write_text(normalized_text, encoding="utf-8")
        return normalized_text

    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_text = _normalize_text_file_content(raw_content)
    path.write_text(normalized_text, encoding="utf-8")
    return normalized_text


def create_admin_blueprint(config: AppConfig) -> Blueprint:
    bp = Blueprint("admin", __name__)
    users_file = config.users_file
    config_files = _build_config_file_items(config)

    @bp.get("/admin")
    def admin_page() -> Any:
        record = _require_admin_page(users_file)
        if record is None:
            if _get_current_user_record(users_file) is None:
                return redirect(url_for("auth.login_page"))
            return redirect(url_for("auth.chat_page"))
        return render_template(
            "admin.html",
            username=record["username"],
            config_files=[_serialize_config_file_item(item) for item in config_files.values()],
        )

    @bp.get("/api/admin/config-files")
    def list_config_files() -> Any:
        _, error_response = _require_admin_api(users_file)
        if error_response is not None:
            return error_response
        return jsonify(
            {
                "ok": True,
                "files": [_serialize_config_file_item(item) for item in config_files.values()],
                "default_file_id": CONFIG_FILE_AUTH_USERS,
            }
        )

    @bp.get("/api/admin/config-files/<file_id>")
    def get_config_file(file_id: str) -> Any:
        _, error_response = _require_admin_api(users_file)
        if error_response is not None:
            return error_response

        try:
            item = _get_config_file_item(config_files, file_id)
            content = _read_config_file_content(item)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        return jsonify(
            {
                "ok": True,
                **_serialize_config_file_item(item),
                "content": content,
            }
        )

    @bp.put("/api/admin/config-files/<file_id>")
    def update_config_file(file_id: str) -> Any:
        current_record, error_response = _require_admin_api(users_file)
        if error_response is not None:
            return error_response

        payload = request.get_json(silent=True) or {}
        raw_content = payload.get("content", "")
        if not isinstance(raw_content, str):
            return jsonify({"ok": False, "error": "配置内容必须是字符串"}), 400

        hot_reload: dict[str, list[str]] | None = None
        try:
            item = _get_config_file_item(config_files, file_id)
            content = _save_config_file_content(
                item,
                raw_content,
                current_username=current_record["username"],
            )
            if item["format"] in {"dotenv", "jsonc"}:
                hot_reload = apply_runtime_config_values(
                    current_app,
                    config,
                    read_env_files_values(config.env_files),
                )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        logger.info(
            "后台保存配置文件成功: 文件ID=%s 路径=%s 热更新=%s",
            file_id,
            item["path"],
            hot_reload,
        )
        response_body: dict[str, Any] = {
            "ok": True,
            **_serialize_config_file_item(item),
            "content": content,
        }
        if hot_reload is not None:
            response_body["hot_reload"] = hot_reload
        return jsonify(response_body)

    @bp.get("/api/admin/auth-config")
    def get_auth_config() -> Any:
        _, error_response = _require_admin_api(users_file)
        if error_response is not None:
            return error_response

        item = config_files[CONFIG_FILE_AUTH_USERS]
        return jsonify(
            {
                "ok": True,
                "path": str(item["path"]),
                "content": _read_config_file_content(item),
            }
        )

    @bp.put("/api/admin/auth-config")
    def update_auth_config() -> Any:
        current_record, error_response = _require_admin_api(users_file)
        if error_response is not None:
            return error_response

        payload = request.get_json(silent=True) or {}
        raw_content = payload.get("content", "")
        if not isinstance(raw_content, str) or not raw_content.strip():
            return jsonify({"ok": False, "error": "配置内容不能为空"}), 400

        item = config_files[CONFIG_FILE_AUTH_USERS]
        try:
            content = _save_config_file_content(
                item,
                raw_content,
                current_username=current_record["username"],
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        return jsonify(
            {
                "ok": True,
                "path": str(item["path"]),
                "content": content,
            }
        )

    return bp
