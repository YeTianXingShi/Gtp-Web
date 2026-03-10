from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from gtpweb.config import AppConfig
from gtpweb.user_store import (
    create_user,
    delete_user,
    get_user_record,
    list_users,
    normalize_users_config,
    save_users_config,
    update_user,
    users_config_to_text,
)

logger = logging.getLogger(__name__)


CONFIG_FILE_AUTH_USERS = "auth_users"
CONFIG_FILE_APP_ENV = "app_env"


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
    return {
        CONFIG_FILE_AUTH_USERS: {
            "id": CONFIG_FILE_AUTH_USERS,
            "label": "认证配置",
            "description": "管理普通用户和管理员账号，保存后立即生效。",
            "path": config.users_file,
            "requires_restart": False,
            "format": "json",
        },
        CONFIG_FILE_APP_ENV: {
            "id": CONFIG_FILE_APP_ENV,
            "label": "应用环境变量",
            "description": "管理 .env 配置，修改后通常需要重启服务才能完全生效。",
            "path": config.env_file,
            "requires_restart": True,
            "format": "dotenv",
        },
    }


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

    @bp.get("/api/admin/users")
    def list_admin_users() -> Any:
        _, error_response = _require_admin_api(users_file)
        if error_response is not None:
            return error_response
        return jsonify({"ok": True, "users": list_users(users_file)})

    @bp.post("/api/admin/users")
    def create_admin_user() -> Any:
        _, error_response = _require_admin_api(users_file)
        if error_response is not None:
            return error_response

        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        is_admin = payload.get("is_admin", False) if isinstance(payload.get("is_admin", False), bool) else False

        try:
            created_user = create_user(users_file, username, password, is_admin)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        logger.info("后台新增用户成功: 用户名=%s 管理员=%s", created_user["username"], created_user["is_admin"])
        return jsonify({"ok": True, "user": created_user}), 201

    @bp.patch("/api/admin/users/<username>")
    def update_admin_user(username: str) -> Any:
        current_record, error_response = _require_admin_api(users_file)
        if error_response is not None:
            return error_response

        payload = request.get_json(silent=True) or {}
        password: str | None = None
        if "password" in payload:
            password = str(payload.get("password", ""))
        is_admin: bool | None = None
        if "is_admin" in payload:
            raw_is_admin = payload.get("is_admin")
            if not isinstance(raw_is_admin, bool):
                return jsonify({"ok": False, "error": "is_admin 必须是布尔值"}), 400
            is_admin = raw_is_admin
        if password is None and is_admin is None:
            return jsonify({"ok": False, "error": "没有可更新的字段"}), 400

        try:
            updated_user = update_user(
                users_file,
                username,
                password=password,
                is_admin=is_admin,
                current_username=current_record["username"],
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        logger.info("后台更新用户成功: 用户名=%s 管理员=%s", updated_user["username"], updated_user["is_admin"])
        return jsonify({"ok": True, "user": updated_user})

    @bp.delete("/api/admin/users/<username>")
    def delete_admin_user(username: str) -> Any:
        current_record, error_response = _require_admin_api(users_file)
        if error_response is not None:
            return error_response

        try:
            delete_user(users_file, username, current_username=current_record["username"])
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        logger.info("后台删除用户成功: 用户名=%s", username)
        return jsonify({"ok": True})

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

        try:
            item = _get_config_file_item(config_files, file_id)
            content = _save_config_file_content(
                item,
                raw_content,
                current_username=current_record["username"],
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        logger.info("后台保存配置文件成功: 文件ID=%s 路径=%s", file_id, item["path"])
        return jsonify(
            {
                "ok": True,
                **_serialize_config_file_item(item),
                "content": content,
            }
        )

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
