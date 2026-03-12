from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def open_db_connection(db_file: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_file: Path) -> None:
    logger.info("数据库初始化开始: 数据库=%s", db_file)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with open_db_connection(db_file) as conn:
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
        message_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        conversation_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(conversations)").fetchall()
        }
        if "reasoning_effort" not in conversation_columns:
            conn.execute(
                "ALTER TABLE conversations ADD COLUMN reasoning_effort TEXT NOT NULL DEFAULT ''"
            )
            logger.info("数据库迁移完成: conversations 表已新增 reasoning_effort 字段")
        if "thinking_level" not in conversation_columns:
            conn.execute(
                "ALTER TABLE conversations ADD COLUMN thinking_level TEXT NOT NULL DEFAULT ''"
            )
            logger.info("数据库迁移完成: conversations 表已新增 thinking_level 字段")
        if "reasoning" not in message_columns:
            conn.execute(
                "ALTER TABLE messages ADD COLUMN reasoning TEXT NOT NULL DEFAULT ''"
            )
            logger.info("数据库迁移完成: messages 表已新增 reasoning 字段")
        if "status" not in message_columns:
            conn.execute(
                "ALTER TABLE messages ADD COLUMN status TEXT NOT NULL DEFAULT 'complete'"
            )
            logger.info("数据库迁移完成: messages 表已新增 status 字段")
        conn.commit()
    logger.info("数据库初始化完成: 数据库=%s", db_file)
