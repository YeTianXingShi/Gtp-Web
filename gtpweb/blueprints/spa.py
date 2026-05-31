"""
SPA 静态资源蓝图

把 Vite 构建产物（位于 static/dist/）暴露给前端：
- 已构建的资源（JS/CSS/图片）按路径 send_from_directory 直出
- 其他路径（前端 React Router 的客户端路由）兜底返回 index.html

蓝图必须最后注册，确保 /api/* 优先匹配。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, send_from_directory

logger = logging.getLogger(__name__)


def create_spa_blueprint(dist_dir: Path) -> Blueprint:
    bp = Blueprint("spa", __name__)

    @bp.get("/")
    @bp.get("/<path:path>")
    def spa(path: str = "") -> Any:
        # 1. 命中真实文件 → 直出静态资源
        if path:
            asset = (dist_dir / path).resolve()
            try:
                asset.relative_to(dist_dir.resolve())
            except ValueError:
                # 防止路径穿越
                logger.warning("拒绝越界访问: 请求路径=%s", path)
                return jsonify({"ok": False, "error": "非法路径"}), 400
            if asset.is_file():
                return send_from_directory(dist_dir, path)

        # 2. 兜底：返回 SPA index.html，由 React Router 接管前端路由
        index = dist_dir / "index.html"
        if not index.is_file():
            return jsonify({
                "ok": False,
                "error": "前端尚未构建。请在 frontend/ 目录执行 pnpm install && pnpm build",
            }), 503
        return send_from_directory(dist_dir, "index.html")

    return bp
