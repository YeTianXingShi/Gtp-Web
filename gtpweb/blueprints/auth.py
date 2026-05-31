"""
认证蓝图模块（JWT 版）

提供基于 JWT 双 Token 的鉴权 API：
- POST /api/login   ：账密登录，返回 access_token 与 user，refresh 通过 HttpOnly Cookie 下发
- POST /api/refresh ：用 refresh cookie 换新的 access_token（并轮转 refresh）
- POST /api/logout  ：撤销当前 refresh，清除 cookie
- GET  /api/me      ：返回当前登录用户信息

magic-login 免密链接机制已废弃。
HTML 页面路由已全部迁移到前端 SPA。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import jwt
from flask import Blueprint, g, jsonify, request

from gtpweb.auth_jwt import (
    ACCESS_TTL,
    REFRESH_TTL,
    clear_refresh_cookie,
    cleanup_expired_revocations,
    decode_token,
    is_refresh_jti_revoked,
    issue_tokens,
    read_refresh_cookie,
    require_login,
    revoke_refresh_jti,
    set_refresh_cookie,
)
from gtpweb.audit import log_audit
from gtpweb.config import AppConfig
from gtpweb.user_store import get_user_record, verify_user_credentials

logger = logging.getLogger(__name__)


def create_auth_blueprint(config: AppConfig) -> Blueprint:
    """创建认证蓝图。"""
    bp = Blueprint("auth", __name__)
    users_file = config.users_file
    db_file = config.db_file

    def _is_secure_request() -> bool:
        return bool(request.is_secure)

    def _serialize_user(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "username": str(record["username"]),
            "is_admin": bool(record.get("is_admin")),
        }

    @bp.post("/api/login")
    def login() -> Any:
        """账密登录，签发 access + refresh。"""
        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        logger.info("登录尝试: 用户名=%s", username or "<empty>")

        if not username or not password:
            logger.warning("登录失败: 参数缺失 用户名=%s", username or "<empty>")
            return jsonify({"ok": False, "error": "账号和密码不能为空"}), 400

        user_record = verify_user_credentials(users_file, username, password)
        if user_record is None:
            logger.warning("登录失败: 账号或密码错误 用户名=%s", username)
            return jsonify({"ok": False, "error": "账号或密码错误"}), 401

        if user_record.get("enabled") is False:
            logger.warning("登录失败: 账号已禁用 用户名=%s", username)
            return jsonify({"ok": False, "error": "账号已被禁用"}), 403

        access, refresh, _refresh_jti, _refresh_exp = issue_tokens(
            username=str(user_record["username"]),
            is_admin=bool(user_record.get("is_admin")),
        )

        # 借登录的机会顺手清一下过期撤销记录，避免无限增长
        cleanup_expired_revocations(db_file)

        response = jsonify(
            {
                "ok": True,
                "access_token": access,
                "expires_in": int(ACCESS_TTL.total_seconds()),
                "user": _serialize_user(user_record),
            }
        )
        set_refresh_cookie(response, refresh, secure=_is_secure_request())
        logger.info("登录成功: 用户名=%s 管理员=%s", username, bool(user_record.get("is_admin")))
        log_audit(
            config.db_file,
            username=username,
            action="login",
            target_type="user",
            target_id=username,
            ip_address=request.remote_addr or "",
        )
        return response

    @bp.post("/api/refresh")
    def refresh() -> Any:
        """用 refresh cookie 换新 access；同时轮转 refresh（旧的加入撤销列表）。"""
        token = read_refresh_cookie()
        if not token:
            return jsonify({"ok": False, "error": "缺少刷新凭证"}), 401

        try:
            payload = decode_token(token, expected_type="refresh")
        except jwt.ExpiredSignatureError:
            return jsonify({"ok": False, "error": "刷新凭证已过期"}), 401
        except jwt.PyJWTError:
            return jsonify({"ok": False, "error": "刷新凭证无效"}), 401

        old_jti = str(payload.get("jti", "")).strip()
        if not old_jti or is_refresh_jti_revoked(db_file, old_jti):
            logger.warning("拒绝已撤销的 refresh: jti=%s", old_jti)
            return jsonify({"ok": False, "error": "刷新凭证已失效"}), 401

        username = str(payload.get("sub", "")).strip()
        if not username:
            return jsonify({"ok": False, "error": "刷新凭证无效"}), 401

        user_record = get_user_record(users_file, username)
        if user_record is None or user_record.get("enabled") is False:
            return jsonify({"ok": False, "error": "账号不存在或已禁用"}), 401

        # 轮转 refresh：旧 jti 撤销，签发新 access + 新 refresh
        old_exp = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
        revoke_refresh_jti(db_file, old_jti, old_exp)

        access, new_refresh, _new_jti, _new_exp = issue_tokens(
            username=username,
            is_admin=bool(user_record.get("is_admin")),
        )

        response = jsonify(
            {
                "ok": True,
                "access_token": access,
                "expires_in": int(ACCESS_TTL.total_seconds()),
                "user": _serialize_user(user_record),
            }
        )
        set_refresh_cookie(response, new_refresh, secure=_is_secure_request())
        return response

    @bp.post("/api/logout")
    def logout() -> Any:
        """登出：撤销当前 refresh + 清空 cookie。允许匿名调用以兜底清理。"""
        token = read_refresh_cookie()
        if token:
            try:
                payload = jwt.decode(
                    token,
                    config.jwt_secret,
                    algorithms=["HS256"],
                    options={"verify_exp": False},
                )
                jti = str(payload.get("jti", "")).strip()
                if jti and payload.get("type") == "refresh":
                    exp_ts = int(payload.get("exp", 0))
                    exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else datetime.now(timezone.utc) + REFRESH_TTL
                    revoke_refresh_jti(db_file, jti, exp_dt)
                    logger.info("退出登录: 用户名=%s jti=%s", payload.get("sub", "<unknown>"), jti)
            except jwt.PyJWTError:
                logger.info("退出登录: refresh cookie 已无效，仅清理 cookie")

        response = jsonify({"ok": True})
        clear_refresh_cookie(response)
        return response

    @bp.get("/api/me")
    @require_login
    def me() -> Any:
        """返回当前登录用户的轻量信息（不含 api_keys 等敏感字段）。"""
        username = g.user["username"]
        record = get_user_record(users_file, username)
        if record is None:
            return jsonify({"ok": False, "error": "用户不存在"}), 401
        return jsonify({"ok": True, "user": _serialize_user(record)})

    return bp
