"""
数据库初始化和管理模块

本模块负责 SQLite 数据库的初始化和表结构维护。

数据库表结构：
- conversations: 对话记录
- messages: 消息记录
- message_attachments: 消息附件
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _add_column_if_missing(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    columns: set[str],
    column_name: str,
    column_sql: str,
) -> None:
    if column_name in columns:
        return

    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")
    columns.add(column_name)
    logger.info("数据库迁移完成: %s 表已新增 %s 字段", table_name, column_name)


def _add_timestamp_column_if_missing(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    columns: set[str],
    column_name: str,
) -> None:
    if column_name in columns:
        return

    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT")
    conn.execute(
        f"UPDATE {table_name} SET {column_name} = CURRENT_TIMESTAMP WHERE {column_name} IS NULL"
    )
    columns.add(column_name)
    logger.info("数据库迁移完成: %s 表已新增 %s 时间字段", table_name, column_name)


def open_db_connection(db_file: Path) -> sqlite3.Connection:
    """
    打开数据库连接

    Args:
        db_file: 数据库文件路径

    Returns:
        sqlite3.Connection: 数据库连接对象，配置了 Row 工厂以支持字典式访问
    """
    conn = sqlite3.connect(db_file)
    # 设置行工厂，使查询结果可以通过列名访问
    conn.row_factory = sqlite3.Row
    # 启用外键约束
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_file: Path) -> None:
    """
    初始化数据库表结构

    创建所有必要的表，并执行数据库迁移（新增字段）。

    数据库表说明：
    1. conversations: 对话记录表
       - id: 主键
       - username: 用户名
       - title: 对话标题
       - model: 使用的模型名称
       - reasoning_effort: OpenAI 推理强度
       - thinking_level: Google Thinking 级别
       - last_response_id: 最后一次响应 ID（用于流式继续）
       - created_at: 创建时间
       - updated_at: 更新时间

    2. messages: 消息记录表
       - id: 主键
       - conversation_id: 所属对话 ID（外键）
       - role: 角色（user/assistant/system）
       - content: 消息内容
       - reasoning: 推理过程文本
       - status: 消息状态（complete/incomplete）
       - created_at: 创建时间

    3. message_attachments: 消息附件表
       - id: 主键
       - message_id: 所属消息 ID（外键）
       - file_name: 文件名
       - file_path: 文件存储路径
       - mime_type: MIME 类型
       - kind: 附件类型（image/text/binary）
       - parsed_text: 解析后的文本内容（文本文件）
       - created_at: 创建时间

    Args:
        db_file: 数据库文件路径

    Returns:
        无
    """
    logger.info("数据库初始化开始: 数据库=%s", db_file)

    # 确保数据库目录存在
    db_file.parent.mkdir(parents=True, exist_ok=True)

    with open_db_connection(db_file) as conn:
        # 创建对话表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '新对话',
                model TEXT NOT NULL,
                reasoning_effort TEXT NOT NULL DEFAULT '',
                thinking_level TEXT NOT NULL DEFAULT '',
                last_response_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 创建消息表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                reasoning TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'complete' CHECK (status IN ('complete', 'incomplete')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )

        # 创建消息附件表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS message_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('image', 'text', 'binary')),
                parsed_text TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pdf_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                original_file_name TEXT NOT NULL,
                storage_path TEXT NOT NULL DEFAULT '',
                display_title TEXT NOT NULL DEFAULT '',
                parse_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (parse_status IN ('pending', 'processing', 'ready', 'failed')),
                parse_error TEXT NOT NULL DEFAULT '',
                parse_warning TEXT NOT NULL DEFAULT '',
                section_source TEXT NOT NULL DEFAULT 'pages'
                    CHECK (section_source IN ('outline', 'toc', 'pages')),
                file_size_bytes INTEGER NOT NULL DEFAULT 0,
                page_count INTEGER NOT NULL DEFAULT 0,
                total_chars INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                parsed_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pdf_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                char_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (document_id, page_number),
                FOREIGN KEY (document_id) REFERENCES pdf_documents(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pdf_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                parent_id INTEGER,
                title TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 1,
                start_page INTEGER NOT NULL,
                end_page INTEGER NOT NULL,
                sort_index INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'outline' CHECK (source IN ('outline', 'toc')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES pdf_documents(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES pdf_sections(id) ON DELETE CASCADE
            )
            """
        )

        # 获取当前表结构，用于数据库迁移
        message_columns = _get_table_columns(conn, "messages")
        conversation_columns = _get_table_columns(conn, "conversations")
        pdf_document_columns = _get_table_columns(conn, "pdf_documents")
        pdf_page_columns = _get_table_columns(conn, "pdf_pages")
        pdf_section_columns = _get_table_columns(conn, "pdf_sections")

        # 数据库迁移：新增 reasoning_effort 字段
        _add_column_if_missing(
            conn,
            table_name="conversations",
            columns=conversation_columns,
            column_name="reasoning_effort",
            column_sql="reasoning_effort TEXT NOT NULL DEFAULT ''",
        )

        # 数据库迁移：新增 thinking_level 字段
        _add_column_if_missing(
            conn,
            table_name="conversations",
            columns=conversation_columns,
            column_name="thinking_level",
            column_sql="thinking_level TEXT NOT NULL DEFAULT ''",
        )

        # 数据库迁移：新增 reasoning 字段
        _add_column_if_missing(
            conn,
            table_name="messages",
            columns=message_columns,
            column_name="reasoning",
            column_sql="reasoning TEXT NOT NULL DEFAULT ''",
        )

        # 数据库迁移：新增 status 字段
        _add_column_if_missing(
            conn,
            table_name="messages",
            columns=message_columns,
            column_name="status",
            column_sql="status TEXT NOT NULL DEFAULT 'complete'",
        )

        # 数据库迁移：补齐 PDF 工作台文档表字段
        _add_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="created_at",
            column_sql="created_at TEXT",
        )
        if "created_at" in pdf_document_columns:
            conn.execute(
                "UPDATE pdf_documents SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
            )

        _add_timestamp_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="updated_at",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="storage_path",
            column_sql="storage_path TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="display_title",
            column_sql="display_title TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="parse_status",
            column_sql="parse_status TEXT NOT NULL DEFAULT 'pending'",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="parse_error",
            column_sql="parse_error TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="parse_warning",
            column_sql="parse_warning TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="section_source",
            column_sql="section_source TEXT NOT NULL DEFAULT 'pages'",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="file_size_bytes",
            column_sql="file_size_bytes INTEGER NOT NULL DEFAULT 0",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="page_count",
            column_sql="page_count INTEGER NOT NULL DEFAULT 0",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="total_chars",
            column_sql="total_chars INTEGER NOT NULL DEFAULT 0",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_documents",
            columns=pdf_document_columns,
            column_name="parsed_at",
            column_sql="parsed_at TEXT",
        )

        # 数据库迁移：补齐 PDF 页表字段
        _add_timestamp_column_if_missing(
            conn,
            table_name="pdf_pages",
            columns=pdf_page_columns,
            column_name="created_at",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_pages",
            columns=pdf_page_columns,
            column_name="text",
            column_sql="text TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_pages",
            columns=pdf_page_columns,
            column_name="char_count",
            column_sql="char_count INTEGER NOT NULL DEFAULT 0",
        )
        # 数据库迁移：补齐 PDF 章节表字段
        _add_timestamp_column_if_missing(
            conn,
            table_name="pdf_sections",
            columns=pdf_section_columns,
            column_name="created_at",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_sections",
            columns=pdf_section_columns,
            column_name="parent_id",
            column_sql="parent_id INTEGER",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_sections",
            columns=pdf_section_columns,
            column_name="level",
            column_sql="level INTEGER NOT NULL DEFAULT 1",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_sections",
            columns=pdf_section_columns,
            column_name="start_page",
            column_sql="start_page INTEGER NOT NULL DEFAULT 1",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_sections",
            columns=pdf_section_columns,
            column_name="end_page",
            column_sql="end_page INTEGER NOT NULL DEFAULT 1",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_sections",
            columns=pdf_section_columns,
            column_name="sort_index",
            column_sql="sort_index INTEGER NOT NULL DEFAULT 0",
        )
        _add_column_if_missing(
            conn,
            table_name="pdf_sections",
            columns=pdf_section_columns,
            column_name="source",
            column_sql="source TEXT NOT NULL DEFAULT 'outline'",
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pdf_documents_username_updated ON pdf_documents (username, updated_at DESC, id DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pdf_pages_document_page ON pdf_pages (document_id, page_number ASC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pdf_sections_document_sort ON pdf_sections (document_id, sort_index ASC)"
        )

        conn.commit()

    logger.info("数据库初始化完成: 数据库=%s", db_file)
