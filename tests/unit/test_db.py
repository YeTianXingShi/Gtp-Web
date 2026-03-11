from __future__ import annotations

import sqlite3

from gtpweb.db import init_db, open_db_connection


def test_init_db_migrates_messages_reasoning_column(tmp_path):
    db_file = tmp_path / "chat.db"

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            """
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '新对话',
                model TEXT NOT NULL,
                last_response_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        cursor = conn.execute(
            """
            INSERT INTO conversations (username, title, model)
            VALUES ('u', '旧会话', 'openai:gpt-4o-mini')
            """
        )
        conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (?, 'assistant', '旧消息')
            """,
            (int(cursor.lastrowid),),
        )
        conn.commit()

    init_db(db_file)

    with open_db_connection(db_file) as conn:
        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        message_row = conn.execute(
            "SELECT content, reasoning FROM messages ORDER BY id ASC LIMIT 1"
        ).fetchone()

    assert "reasoning" in columns
    assert message_row["content"] == "旧消息"
    assert message_row["reasoning"] == ""
