"""
Gtp-Web 应用启动入口

本文件是 Gtp-Web 项目的入口文件，负责创建并启动 Flask Web 应用。
应用工厂模式允许在测试或生产环境中灵活配置应用。
"""

from __future__ import annotations

import logging
import os

from gtpweb import create_app


# 创建 Flask 应用实例
app = create_app()
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    # 监听所有网络接口
    host = "0.0.0.0"
    # 从环境变量获取端口号，默认 8000
    port = int(os.getenv("PORT", "8000"))
    # 从环境变量获取调试模式，默认开启
    debug = os.getenv("FLASK_DEBUG", "1").strip() in {"1", "true", "yes", "on"}

    logger.info("启动 Web 服务: host=%s port=%s debug=%s", host, port, debug)
    # 启动开发服务器
    app.run(host=host, port=port, debug=debug)
