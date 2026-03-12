"""
日志配置模块

配置应用的日志系统，包括：
- 多文件日志归档（按模块分类）
- 请求日志记录
- 请求上下文过滤
- 日志轮转
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

from flask import Flask, g, has_request_context, request, session

from gtpweb.config import AppConfig

# 敏感请求头（需要脱敏）
SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
}


class MaxLevelFilter(logging.Filter):
    """
    最大日志级别过滤器

    只允许不超过指定级别的日志通过。

    Attributes:
        max_level: 最大允许的日志级别
    """
    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


class RequestContextFilter(logging.Filter):
    """
    请求上下文过滤器

    为日志记录添加请求 ID 和用户名。

    Attributes:
        无
    """
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = "-"
        record.username = "-"
        if has_request_context():
            record.request_id = str(getattr(g, "request_id", "-") or "-")
            username = session.get("username")
            if isinstance(username, str) and username:
                record.username = username
        return True


def _build_formatter() -> logging.Formatter:
    """
    构建日志格式化器

    Returns:
        配置好的格式化器
    """
    return logging.Formatter(
        fmt=(
            "%(asctime)s %(levelname)s [%(name)s] "
            "[请求ID=%(request_id)s 用户=%(username)s] %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _sanitize_headers(raw_headers: dict[str, str]) -> dict[str, str]:
    """
    脱敏请求头

    隐藏敏感请求头，截断过长的请求头值。

    Args:
        raw_headers: 原始请求头字典

    Returns:
        脱敏后的请求头字典
    """
    sanitized: dict[str, str] = {}
    for key, value in raw_headers.items():
        lower_key = key.lower()
        if lower_key in SENSITIVE_HEADERS:
            sanitized[key] = "***"
            continue
        if len(value) > 180:
            sanitized[key] = f"{value[:180]}...(已截断, 原始长度={len(value)})"
            continue
        sanitized[key] = value
    return sanitized


def _make_rotating_file_handler(
    path: Path,
    level: int,
    formatter: logging.Formatter,
    context_filter: logging.Filter,
    *,
    extra_filters: Iterable[logging.Filter] | None = None,
    max_bytes: int,
    backup_count: int,
) -> RotatingFileHandler:
    """
    创建轮转文件处理器

    Args:
        path: 日志文件路径
        level: 日志级别
        formatter: 格式化器
        context_filter: 上下文过滤器
        extra_filters: 额外的过滤器列表
        max_bytes: 单个日志文件最大字节数
        backup_count: 备份文件数量

    Returns:
        配置好的轮转文件处理器
    """
    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    handler.addFilter(context_filter)
    if extra_filters:
        for extra_filter in extra_filters:
            handler.addFilter(extra_filter)
    return handler


def _reset_logger(logger: logging.Logger) -> None:
    """
    重置日志处理器

    移除并关闭所有现有的处理器。

    Args:
        logger: 日志记录器

    Returns:
        无
    """
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def _configure_named_logger(
    *,
    name: str,
    level: int,
    formatter: logging.Formatter,
    context_filter: logging.Filter,
    file_path: Path,
    max_bytes: int,
    backup_count: int,
    propagate: bool = True,
) -> None:
    """
    配置命名日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别
        formatter: 格式化器
        context_filter: 上下文过滤器
        file_path: 日志文件路径
        max_bytes: 单个日志文件最大字节数
        backup_count: 备份文件数量
        propagate: 是否传播到根日志记录器

    Returns:
        无
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = propagate
    _reset_logger(logger)
    logger.addHandler(
        _make_rotating_file_handler(
            file_path,
            level,
            formatter,
            context_filter,
            max_bytes=max_bytes,
            backup_count=backup_count,
        )
    )


def configure_logging(config: AppConfig) -> None:
    """
    配置应用日志系统

    创建多个日志文件：
    - app.log: 启动和基础设施日志（INFO 及以下）
    - error.log: 所有模块的 WARNING 和 ERROR 日志
    - request.log: HTTP 请求日志
    - auth.log: 认证相关日志
    - conversation.log: 对话管理日志
    - chat.log: 聊天相关日志

    Args:
        config: 应用配置

    Returns:
        无
    """
    level = getattr(logging, config.log_level, logging.INFO)
    formatter = _build_formatter()
    context_filter = RequestContextFilter()

    # 配置根日志记录器
    root = logging.getLogger()
    root.setLevel(level)
    _reset_logger(root)

    # 确定日志目录
    base_log_path = config.log_file
    if not base_log_path.is_absolute():
        base_log_path = Path.cwd() / base_log_path
    log_dir = base_log_path.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # 添加控制台输出
    if config.log_to_stdout:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(context_filter)
        root.addHandler(console_handler)

    # Error archive: 所有模块的 WARNING 和 ERROR 日志
    root.addHandler(
        _make_rotating_file_handler(
            log_dir / "error.log",
            logging.WARNING,
            formatter,
            context_filter,
            max_bytes=config.log_max_bytes,
            backup_count=config.log_backup_count,
        )
    )

    # 按模块分类的日志文件
    _configure_named_logger(
        name="gtpweb.request",
        level=level,
        formatter=formatter,
        context_filter=context_filter,
        file_path=log_dir / "request.log",
        max_bytes=config.log_max_bytes,
        backup_count=config.log_backup_count,
    )
    _configure_named_logger(
        name="gtpweb.blueprints.auth",
        level=level,
        formatter=formatter,
        context_filter=context_filter,
        file_path=log_dir / "auth.log",
        max_bytes=config.log_max_bytes,
        backup_count=config.log_backup_count,
    )
    _configure_named_logger(
        name="gtpweb.blueprints.conversation",
        level=level,
        formatter=formatter,
        context_filter=context_filter,
        file_path=log_dir / "conversation.log",
        max_bytes=config.log_max_bytes,
        backup_count=config.log_backup_count,
    )
    _configure_named_logger(
        name="gtpweb.blueprints.chat",
        level=level,
        formatter=formatter,
        context_filter=context_filter,
        file_path=log_dir / "chat.log",
        max_bytes=config.log_max_bytes,
        backup_count=config.log_backup_count,
    )

    # Core archive: 启动和基础设施日志（INFO 及以下）
    app_filter = MaxLevelFilter(logging.INFO)
    app_handler = _make_rotating_file_handler(
        base_log_path,
        level,
        formatter,
        context_filter,
        extra_filters=[app_filter],
        max_bytes=config.log_max_bytes,
        backup_count=config.log_backup_count,
    )
    for logger_name in ["gtpweb.app_factory", "gtpweb.db", "__main__", "gtpweb.logging"]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = True
        _reset_logger(logger)
        logger.addHandler(app_handler)

    # 记录初始化完成
    startup_logger = logging.getLogger("gtpweb.logging")
    startup_logger.info(
        "日志系统初始化完成: 级别=%s 日志目录=%s 控制台输出=%s 滚动大小=%s 备份份数=%s "
        "分类文件=[app.log,request.log,auth.log,conversation.log,chat.log,error.log]",
        config.log_level,
        log_dir,
        config.log_to_stdout,
        config.log_max_bytes,
        config.log_backup_count,
    )


def register_request_logging(app: Flask) -> None:
    """
    注册请求日志钩子

    记录每个 HTTP 请求的开始和结束。

    Args:
        app: Flask 应用实例

    Returns:
        无
    """
    logger = logging.getLogger("gtpweb.request")

    @app.before_request
    def _log_request_start() -> None:
        """请求开始前记录"""
        g.request_id = request.headers.get("X-Request-ID", str(uuid4()))
        g.request_started_at = time.perf_counter()
        sanitized_headers = _sanitize_headers(dict(request.headers.items()))
        logger.info(
            "请求开始: 方法=%s 路径=%s 查询=%s 内容类型=%s 内容长度=%s 来源IP=%s UserAgent=%s",
            request.method,
            request.path,
            request.query_string.decode("utf-8", errors="ignore"),
            request.content_type or "",
            request.content_length,
            request.remote_addr,
            request.user_agent.string,
        )
        logger.debug("请求头(已脱敏): %s", sanitized_headers)

    @app.after_request
    def _log_request_end(response):
        """请求结束后记录"""
        duration_ms = -1.0
        started_at = getattr(g, "request_started_at", None)
        if isinstance(started_at, float):
            duration_ms = (time.perf_counter() - started_at) * 1000

        request_id = str(getattr(g, "request_id", ""))
        if request_id:
            response.headers["X-Request-ID"] = request_id

        if response.is_streamed:
            response_bytes: str | int | None = "streamed"
        else:
            response_bytes = response.calculate_content_length()

        logger.info(
            "请求结束: 方法=%s 路径=%s 状态码=%s 耗时毫秒=%.2f 响应字节=%s 响应类型=%s",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            response_bytes,
            response.content_type,
        )
        return response

    @app.teardown_request
    def _log_request_teardown(exc: BaseException | None) -> None:
        """请求清理时记录异常"""
        if exc is not None:
            if isinstance(exc, GeneratorExit):
                logger.info("请求连接已关闭: 路径=%s（客户端中断或刷新）", request.path)
                return
            logger.exception("请求异常: 路径=%s 错误=%s", request.path, exc)
