"""
认证蓝图模块

本模块处理用户认证相关的路由和功能，包括：
- 用户登录和登出
- 会话管理
- 访问控制（普通用户/管理员）
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from gtpweb.ai_providers import build_model_groups, serialize_model_options
from gtpweb.config import AppConfig
from gtpweb.runtime_state import get_runtime_state
from gtpweb.user_store import get_user_record, verify_user_credentials

logger = logging.getLogger(__name__)


def _get_current_user_record(users_file: Path) -> dict[str, Any] | None:
    """
    获取当前用户的完整记录

    Args:
        users_file: 用户配置文件路径

    Returns:
        用户记录字典，未登录或用户不存在则返回 None
    """
    username = session.get("username")
    if not isinstance(username, str) or not username:
        return None

    record = get_user_record(users_file, username)
    if record is None:
        logger.warning("会话用户不存在，已清理登录态: 用户名=%s", username)
        session.clear()
        return None
    return record


def _get_current_user(users_file: Path) -> str | None:
    """
    获取当前用户名

    Args:
        users_file: 用户配置文件路径

    Returns:
        当前用户名，未登录则返回 None
    """
    record = _get_current_user_record(users_file)
    if record is None:
        return None
    return str(record["username"])


def _build_magic_login_redirect(record: dict[str, Any]) -> str:
    if record.get("is_admin"):
        return "/admin"
    return "/chat"



def create_auth_blueprint(config: AppConfig) -> Blueprint:
    """
    创建认证蓝图

    Args:
        config: 应用配置

    Returns:
        Flask 蓝图对象
    """
    bp = Blueprint("auth", __name__)
    users_file = config.users_file
    magic_login_serializer = URLSafeTimedSerializer(config.magic_login_secret, salt="magic-login")

    @bp.get("/")
    def index() -> Any:
        """
        根路径处理

        根据用户角色重定向到相应页面：
        - 未登录 → 登录页
        - 管理员 → 管理页面
        - 普通用户 → 聊天页面

        Returns:
            重定向响应
        """
        record = _get_current_user_record(users_file)
        if record is None:
            return redirect(url_for("auth.login_page"))
        if record["is_admin"]:
            return redirect(url_for("admin.admin_page"))
        return redirect(url_for("auth.chat_page"))

    @bp.get("/login")
    def login_page() -> str:
        """
        登录页面

        如果已登录则重定向到相应页面。

        Returns:
            登录页面 HTML 或重定向响应
        """
        record = _get_current_user_record(users_file)
        if record is not None:
            if record["is_admin"]:
                return redirect(url_for("admin.admin_page"))
            return redirect(url_for("auth.chat_page"))
        return render_template("login.html")

    @bp.get("/login/magic")
    def magic_login() -> Any:
        token = str(request.args.get("token", "")).strip()
        next_url = str(request.args.get("next", "")).strip()
        if not token:
            abort(400, description="缺少 token")

        try:
            payload = magic_login_serializer.loads(
                token,
                max_age=config.magic_login_default_max_age,
            )
        except SignatureExpired:
            logger.warning("免登录失败: 链接已过期")
            abort(401, description="免登录链接已过期")
        except BadSignature:
            logger.warning("免登录失败: token 无效")
            abort(401, description="免登录链接无效")

        if not isinstance(payload, dict):
            abort(401, description="免登录链接无效")

        username = str(payload.get("username", "")).strip()
        if not username:
            abort(401, description="免登录链接无效")

        record = get_user_record(users_file, username)
        if record is None:
            logger.warning("免登录失败: 用户不存在 用户名=%s", username)
            abort(404, description="用户不存在")

        session.clear()
        session.permanent = True
        session["username"] = record["username"]
        redirect_to = next_url or str(payload.get("next", "")).strip() or _build_magic_login_redirect(record)
        if not redirect_to.startswith("/"):
            redirect_to = _build_magic_login_redirect(record)
        logger.info("免登录成功: 用户名=%s 管理员=%s", username, record["is_admin"])
        return redirect(redirect_to)

    @bp.post("/api/login")
    def login() -> Any:
        """
        登录 API

        验证用户凭据并创建会话。

        Returns:
            JSON 响应，包含登录结果和重定向目标
        """
        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        logger.info("登录尝试: 用户名=%s", username or "<empty>")

        # 参数验证
        if not username or not password:
            logger.warning("登录失败: 参数缺失 用户名=%s", username or "<empty>")
            return jsonify({"ok": False, "error": "账号和密码不能为空"}), 400

        # 验证凭据
        user_record = verify_user_credentials(users_file, username, password)
        if user_record is None:
            logger.warning("登录失败: 账号或密码错误 用户名=%s", username)
            return jsonify({"ok": False, "error": "账号或密码错误"}), 401

        # 创建会话
        session.permanent = True
        session["username"] = user_record["username"]
        logger.info("登录成功: 用户名=%s 管理员=%s", username, user_record["is_admin"])

        return jsonify(
            {
                "ok": True,
                "is_admin": bool(user_record["is_admin"]),
                "redirect_to": _build_magic_login_redirect(user_record),
            }
        )

    @bp.post("/api/logout")
    def logout() -> Any:
        """
        登出 API

        清除当前会话。

        Returns:
            JSON 响应
        """
        username = _get_current_user(users_file) or "<anonymous>"
        logger.info("退出登录: 用户名=%s", username)
        session.clear()
        return jsonify({"ok": True})

    @bp.get("/chat")
    def chat_page() -> Any:
        """
        聊天页面

        需要用户登录才能访问。
        渲染聊天页面并传递模型配置。

        Returns:
            聊天页面 HTML 或重定向响应
        """
        record = _get_current_user_record(users_file)
        if record is None:
            return redirect(url_for("auth.login_page"))

        # 获取运行时配置
        runtime_settings = get_runtime_state().settings

        return render_template(
            "chat.html",
            username=record["username"],
            is_admin=bool(record["is_admin"]),
            models=runtime_settings.models,
            model_groups=build_model_groups(runtime_settings.model_options),
            model_options=serialize_model_options(runtime_settings.model_options),
            max_attachments_per_message=runtime_settings.max_attachments_per_message,
            max_upload_mb=runtime_settings.max_upload_mb,
            allowed_attachment_exts=sorted(runtime_settings.allowed_attachment_exts),
        )

    return bp
