from __future__ import annotations

from gtpweb.db import init_db, open_db_connection
from gtpweb.pdf_workbench import (
    PDF_PARSE_STAGE_INTERRUPTED,
    PDF_PARSE_STATUS_FAILED,
    PDF_PARSE_STATUS_READY,
    PDF_SECTION_SOURCE_TOC,
    ParsedPdfDocument,
    ParsedPdfPage,
    ParsedPdfSection,
)
from gtpweb.pdf_workbench_tasks import recover_incomplete_pdf_documents, run_pdf_parse_job


def test_run_pdf_parse_job_marks_document_ready_and_persists_content(tmp_path, monkeypatch):
    db_file = tmp_path / "chat.db"
    pdf_file = tmp_path / "uploads" / "sample.pdf"
    pdf_file.parent.mkdir(parents=True, exist_ok=True)
    pdf_file.write_bytes(b"%PDF-1.4 fake")
    init_db(db_file)

    with open_db_connection(db_file) as conn:
        cursor = conn.execute(
            """
            INSERT INTO pdf_documents (
                username, original_file_name, storage_path, display_title,
                parse_status, parse_progress, parse_stage, parse_error, parse_warning, section_source,
                file_size_bytes, page_count, total_chars, created_at, updated_at
            )
            VALUES (
                'u', 'sample.pdf', ?, 'sample',
                'pending', 0, '等待后台任务排队', '', '', 'pages',
                12, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            (str(pdf_file),),
        )
        document_id = int(cursor.lastrowid)
        conn.commit()

    def _fake_parse(_file_path, *, display_name="", progress_callback=None):
        if progress_callback is not None:
            progress_callback(12, "正在读取 PDF 页面")
            progress_callback(70, "正在识别章节结构")
        return ParsedPdfDocument(
            display_title=display_name or "sample",
            page_count=2,
            total_chars=8,
            section_source=PDF_SECTION_SOURCE_TOC,
            pages=(
                ParsedPdfPage(page_number=1, text="第一页", char_count=3),
                ParsedPdfPage(page_number=2, text="第二页", char_count=3),
            ),
            sections=(
                ParsedPdfSection(
                    title="第一章",
                    level=1,
                    start_page=1,
                    end_page=2,
                    sort_index=1,
                    parent_sort_index=None,
                    source=PDF_SECTION_SOURCE_TOC,
                ),
            ),
            warnings=("已使用目录识别",),
        )

    monkeypatch.setattr("gtpweb.pdf_workbench_tasks.parse_pdf_document", _fake_parse)

    run_pdf_parse_job(
        db_file=db_file,
        document_id=document_id,
        username="u",
        storage_path=pdf_file,
        file_size_bytes=12,
        display_title="sample",
    )

    with open_db_connection(db_file) as conn:
        document_row = conn.execute(
            """
            SELECT parse_status, parse_progress, parse_stage, parse_warning, page_count, total_chars, section_source
            FROM pdf_documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
        page_rows = conn.execute(
            "SELECT page_number, text FROM pdf_pages WHERE document_id = ? ORDER BY page_number ASC",
            (document_id,),
        ).fetchall()
        section_row = conn.execute(
            "SELECT title, start_page, end_page FROM pdf_sections WHERE document_id = ?",
            (document_id,),
        ).fetchone()

    assert document_row["parse_status"] == PDF_PARSE_STATUS_READY
    assert document_row["parse_progress"] == 100
    assert document_row["parse_stage"] == "解析完成"
    assert document_row["parse_warning"] == "已使用目录识别"
    assert document_row["page_count"] == 2
    assert document_row["total_chars"] == 8
    assert document_row["section_source"] == PDF_SECTION_SOURCE_TOC
    assert [tuple(row) for row in page_rows] == [(1, "第一页"), (2, "第二页")]
    assert tuple(section_row) == ("第一章", 1, 2)


def test_run_pdf_parse_job_marks_document_failed_when_parse_raises(tmp_path, monkeypatch):
    db_file = tmp_path / "chat.db"
    pdf_file = tmp_path / "uploads" / "broken.pdf"
    pdf_file.parent.mkdir(parents=True, exist_ok=True)
    pdf_file.write_bytes(b"%PDF-1.4 broken")
    init_db(db_file)

    with open_db_connection(db_file) as conn:
        cursor = conn.execute(
            """
            INSERT INTO pdf_documents (
                username, original_file_name, storage_path, display_title,
                parse_status, parse_progress, parse_stage, parse_error, parse_warning, section_source,
                file_size_bytes, page_count, total_chars, created_at, updated_at
            )
            VALUES (
                'u', 'broken.pdf', ?, 'broken',
                'pending', 0, '等待后台任务排队', '', '', 'pages',
                15, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            (str(pdf_file),),
        )
        document_id = int(cursor.lastrowid)
        conn.commit()

    def _raise_parse_error(_file_path, *, display_name="", progress_callback=None):
        if progress_callback is not None:
            progress_callback(33, "正在读取 PDF 页面")
        raise ValueError("未提取到可用文本")

    monkeypatch.setattr("gtpweb.pdf_workbench_tasks.parse_pdf_document", _raise_parse_error)

    run_pdf_parse_job(
        db_file=db_file,
        document_id=document_id,
        username="u",
        storage_path=pdf_file,
        file_size_bytes=15,
        display_title="broken",
    )

    with open_db_connection(db_file) as conn:
        document_row = conn.execute(
            "SELECT parse_status, parse_progress, parse_stage, parse_error FROM pdf_documents WHERE id = ?",
            (document_id,),
        ).fetchone()

    assert document_row["parse_status"] == PDF_PARSE_STATUS_FAILED
    assert document_row["parse_progress"] == 33
    assert document_row["parse_stage"] == "解析失败"
    assert "未提取到可用文本" in document_row["parse_error"]


def test_recover_incomplete_pdf_documents_marks_pending_and_processing_as_failed(tmp_path):
    db_file = tmp_path / "chat.db"
    init_db(db_file)

    with open_db_connection(db_file) as conn:
        conn.execute(
            """
            INSERT INTO pdf_documents (
                username, original_file_name, display_title,
                parse_status, parse_progress, parse_stage, created_at, updated_at
            )
            VALUES ('u', 'pending.pdf', 'pending', 'pending', 10, '等待后台任务排队', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        conn.execute(
            """
            INSERT INTO pdf_documents (
                username, original_file_name, display_title,
                parse_status, parse_progress, parse_stage, created_at, updated_at
            )
            VALUES ('u', 'processing.pdf', 'processing', 'processing', 45, '正在提取文本', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        conn.commit()

    recover_incomplete_pdf_documents(db_file)

    with open_db_connection(db_file) as conn:
        rows = conn.execute(
            "SELECT original_file_name, parse_status, parse_progress, parse_stage, parse_error FROM pdf_documents ORDER BY id ASC"
        ).fetchall()

    assert [row["parse_status"] for row in rows] == [PDF_PARSE_STATUS_FAILED, PDF_PARSE_STATUS_FAILED]
    assert [row["parse_progress"] for row in rows] == [0, 0]
    assert [row["parse_stage"] for row in rows] == [PDF_PARSE_STAGE_INTERRUPTED, PDF_PARSE_STAGE_INTERRUPTED]
    assert all("后台解析任务已中断" in row["parse_error"] for row in rows)
