from __future__ import annotations

import atexit
import logging
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path
from typing import Any

from gtpweb.db import open_db_connection
from gtpweb.pdf_workbench import (
    PDF_PARSE_STAGE_FAILED,
    PDF_PARSE_STAGE_INTERRUPTED,
    PDF_PARSE_STAGE_PROCESSING,
    PDF_PARSE_STAGE_READY,
    PDF_PARSE_STATUS_FAILED,
    PDF_PARSE_STATUS_PENDING,
    PDF_PARSE_STATUS_PROCESSING,
    PDF_PARSE_STATUS_READY,
    ParsedPdfDocument,
    parse_pdf_document,
)

logger = logging.getLogger(__name__)

_PDF_PARSE_EXECUTOR = ProcessPoolExecutor(max_workers=1)


def _shutdown_executor() -> None:
    _PDF_PARSE_EXECUTOR.shutdown(wait=False, cancel_futures=True)


atexit.register(_shutdown_executor)


def _persist_processing_state(
    conn: Any,
    document_id: int,
    *,
    progress: int,
    stage: str,
) -> None:
    conn.execute(
        """
        UPDATE pdf_documents
        SET parse_status = ?, parse_progress = ?, parse_stage = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            PDF_PARSE_STATUS_PROCESSING,
            max(0, min(99, int(progress))),
            stage.strip() or PDF_PARSE_STAGE_PROCESSING,
            document_id,
        ),
    )
    conn.commit()


def _persist_ready_state(
    conn: Any,
    document_id: int,
    *,
    parsed: ParsedPdfDocument,
    file_size_bytes: int,
) -> None:
    conn.execute(
        """
        UPDATE pdf_documents
        SET display_title = ?, parse_status = ?, parse_progress = 100, parse_stage = ?,
            parse_error = '', parse_warning = ?, section_source = ?, file_size_bytes = ?,
            page_count = ?, total_chars = ?, parsed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            parsed.display_title[:120],
            PDF_PARSE_STATUS_READY,
            PDF_PARSE_STAGE_READY,
            "\n".join(parsed.warnings),
            parsed.section_source,
            file_size_bytes,
            parsed.page_count,
            parsed.total_chars,
            document_id,
        ),
    )
    conn.commit()


def _persist_failed_state(
    conn: Any,
    document_id: int,
    *,
    error_message: str,
    progress: int,
) -> None:
    conn.execute("DELETE FROM pdf_pages WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM pdf_sections WHERE document_id = ?", (document_id,))
    conn.execute(
        """
        UPDATE pdf_documents
        SET parse_status = ?, parse_progress = ?, parse_stage = ?, parse_error = ?, parse_warning = '',
            section_source = 'pages', page_count = 0, total_chars = 0,
            parsed_at = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            PDF_PARSE_STATUS_FAILED,
            max(0, min(99, int(progress))),
            PDF_PARSE_STAGE_FAILED,
            error_message[:500],
            document_id,
        ),
    )
    conn.commit()


def _write_parsed_document(
    conn: Any,
    document_id: int,
    *,
    parsed: ParsedPdfDocument,
    report_progress: Any,
) -> None:
    conn.execute("DELETE FROM pdf_pages WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM pdf_sections WHERE document_id = ?", (document_id,))
    conn.commit()

    total_pages = len(parsed.pages)
    if total_pages <= 0:
        report_progress(96, "正在准备章节数据")
    else:
        for index, page in enumerate(parsed.pages, start=1):
            conn.execute(
                """
                INSERT INTO pdf_pages (document_id, page_number, text, char_count, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (document_id, page.page_number, page.text, page.char_count),
            )
            progress = 90 + round(index / total_pages * 6)
            report_progress(progress, f"正在写入页面数据（{index}/{total_pages}）")

    section_id_by_sort: dict[int, int] = {}
    total_sections = len(parsed.sections)
    if total_sections <= 0:
        report_progress(99, "正在完成解析收尾")
        return

    for index, section in enumerate(parsed.sections, start=1):
        parent_id = (
            section_id_by_sort.get(section.parent_sort_index)
            if section.parent_sort_index is not None
            else None
        )
        cursor = conn.execute(
            """
            INSERT INTO pdf_sections (
                document_id, parent_id, title, level, start_page, end_page, sort_index, source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                document_id,
                parent_id,
                section.title[:200],
                section.level,
                section.start_page,
                section.end_page,
                section.sort_index,
                section.source,
            ),
        )
        section_id_by_sort[section.sort_index] = int(cursor.lastrowid)
        progress = 97 + round(index / total_sections * 2)
        report_progress(progress, f"正在写入章节数据（{index}/{total_sections}）")


def run_pdf_parse_job(
    *,
    db_file: Path,
    document_id: int,
    username: str,
    storage_path: Path,
    file_size_bytes: int,
    display_title: str,
) -> None:
    logger.info("PDF 后台解析任务开始: 用户=%s 文档ID=%s 文件=%s", username, document_id, storage_path)

    with open_db_connection(db_file) as conn:
        last_progress = 0
        last_stage = ""

        def report_progress(progress: int, stage: str) -> None:
            nonlocal last_progress, last_stage

            next_progress = max(last_progress, min(99, int(progress)))
            next_stage = stage.strip() or last_stage or PDF_PARSE_STAGE_PROCESSING
            if next_progress == last_progress and next_stage == last_stage:
                return

            last_progress = next_progress
            last_stage = next_stage
            _persist_processing_state(
                conn,
                document_id,
                progress=next_progress,
                stage=next_stage,
            )

        try:
            if not storage_path.exists():
                raise FileNotFoundError("PDF 文件不存在，无法开始解析。")

            report_progress(1, "后台任务已启动")
            parsed = parse_pdf_document(
                storage_path,
                display_name=display_title,
                progress_callback=report_progress,
            )
            report_progress(90, "正在写入页面数据")
            _write_parsed_document(
                conn,
                document_id,
                parsed=parsed,
                report_progress=report_progress,
            )
            _persist_ready_state(
                conn,
                document_id,
                parsed=parsed,
                file_size_bytes=file_size_bytes,
            )
            logger.info(
                "PDF 后台解析任务完成: 用户=%s 文档ID=%s 页数=%s 字符数=%s",
                username,
                document_id,
                parsed.page_count,
                parsed.total_chars,
            )
        except Exception as exc:
            error_message = str(exc).strip() or "PDF 解析失败"
            logger.exception("PDF 后台解析任务失败: 用户=%s 文档ID=%s", username, document_id)
            _persist_failed_state(
                conn,
                document_id,
                error_message=error_message,
                progress=max(1, last_progress),
            )


def enqueue_pdf_parse_job(
    *,
    db_file: Path,
    document_id: int,
    username: str,
    storage_path: Path,
    file_size_bytes: int,
    display_title: str,
) -> Future[Any]:
    return _PDF_PARSE_EXECUTOR.submit(
        run_pdf_parse_job,
        db_file=db_file,
        document_id=document_id,
        username=username,
        storage_path=storage_path,
        file_size_bytes=file_size_bytes,
        display_title=display_title,
    )


def recover_incomplete_pdf_documents(db_file: Path) -> None:
    with open_db_connection(db_file) as conn:
        cursor = conn.execute(
            """
            UPDATE pdf_documents
            SET parse_status = ?, parse_progress = 0, parse_stage = ?, parse_error = ?,
                parse_warning = '', parsed_at = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE parse_status IN (?, ?)
            """,
            (
                PDF_PARSE_STATUS_FAILED,
                PDF_PARSE_STAGE_INTERRUPTED,
                "后台解析任务已中断，请重新上传 PDF。",
                PDF_PARSE_STATUS_PENDING,
                PDF_PARSE_STATUS_PROCESSING,
            ),
        )
        conn.commit()

    if cursor.rowcount:
        logger.warning("已恢复中断的 PDF 解析任务: 数量=%s 数据库=%s", cursor.rowcount, db_file)
