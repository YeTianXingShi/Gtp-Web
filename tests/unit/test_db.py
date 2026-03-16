from __future__ import annotations

import sqlite3

from gtpweb.db import init_db, open_db_connection


def test_init_db_migrates_messages_reasoning_and_status_columns(tmp_path):
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
            "SELECT content, reasoning, status FROM messages ORDER BY id ASC LIMIT 1"
        ).fetchone()

    assert "reasoning" in columns
    assert "status" in columns
    assert message_row["content"] == "旧消息"
    assert message_row["reasoning"] == ""
    assert message_row["status"] == "complete"


def test_init_db_creates_pdf_workbench_tables(tmp_path):
    db_file = tmp_path / "chat.db"

    init_db(db_file)

    with open_db_connection(db_file) as conn:
        table_names = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        document_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(pdf_documents)").fetchall()
        }
        section_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(pdf_sections)").fetchall()
        }

    assert "pdf_documents" in table_names
    assert "pdf_pages" in table_names
    assert "pdf_sections" in table_names
    assert {"parse_status", "section_source", "page_count", "total_chars"}.issubset(document_columns)
    assert {"parent_id", "start_page", "end_page", "sort_index"}.issubset(section_columns)
