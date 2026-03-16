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
    assert {"parse_status", "parse_progress", "parse_stage", "section_source", "page_count", "total_chars"}.issubset(document_columns)
    assert {"parent_id", "start_page", "end_page", "sort_index"}.issubset(section_columns)


def test_init_db_migrates_existing_pdf_workbench_tables(tmp_path):
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
        conn.execute(
            """
            CREATE TABLE pdf_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                original_file_name TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE pdf_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE pdf_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                title TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO pdf_documents (username, original_file_name)
            VALUES ('alice', 'legacy.pdf')
            """
        )
        conn.execute(
            """
            INSERT INTO pdf_pages (document_id, page_number)
            VALUES (1, 7)
            """
        )
        conn.execute(
            """
            INSERT INTO pdf_sections (document_id, title)
            VALUES (1, '旧章节')
            """
        )
        conn.commit()

    init_db(db_file)

    with open_db_connection(db_file) as conn:
        document_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(pdf_documents)").fetchall()
        }
        page_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(pdf_pages)").fetchall()
        }
        section_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(pdf_sections)").fetchall()
        }
        document_row = conn.execute(
            """
            SELECT username, original_file_name, created_at, updated_at, display_title, parse_status,
                   parse_progress, parse_stage, section_source
            FROM pdf_documents
            WHERE id = 1
            """
        ).fetchone()
        page_row = conn.execute(
            """
            SELECT page_number, text, char_count
            FROM pdf_pages
            WHERE document_id = 1
            """
        ).fetchone()
        section_row = conn.execute(
            """
            SELECT title, parent_id, start_page, end_page, sort_index, source
            FROM pdf_sections
            WHERE document_id = 1
            """
        ).fetchone()

    assert {
        "created_at",
        "storage_path",
        "display_title",
        "parse_status",
        "parse_progress",
        "parse_stage",
        "parse_error",
        "parse_warning",
        "section_source",
        "file_size_bytes",
        "page_count",
        "total_chars",
        "updated_at",
        "parsed_at",
    }.issubset(document_columns)
    assert {"text", "char_count", "created_at"}.issubset(page_columns)
    assert {"parent_id", "level", "start_page", "end_page", "sort_index", "source", "created_at"}.issubset(
        section_columns
    )
    assert document_row["username"] == "alice"
    assert document_row["original_file_name"] == "legacy.pdf"
    assert document_row["created_at"]
    assert document_row["updated_at"]
    assert document_row["display_title"] == ""
    assert document_row["parse_status"] == "pending"
    assert document_row["parse_progress"] == 0
    assert document_row["parse_stage"] == ""
    assert document_row["section_source"] == "pages"
    assert page_row["page_number"] == 7
    assert page_row["text"] == ""
    assert page_row["char_count"] == 0
    assert section_row["title"] == "旧章节"
    assert section_row["parent_id"] is None
    assert section_row["start_page"] == 1
    assert section_row["end_page"] == 1
    assert section_row["sort_index"] == 0
    assert section_row["source"] == "outline"
