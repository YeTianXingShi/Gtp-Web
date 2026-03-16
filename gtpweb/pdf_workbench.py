from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from gtpweb.attachments import normalize_extracted_text

logger = logging.getLogger(__name__)

PDF_PARSE_STATUS_PENDING = "pending"
PDF_PARSE_STATUS_PROCESSING = "processing"
PDF_PARSE_STATUS_READY = "ready"
PDF_PARSE_STATUS_FAILED = "failed"

PDF_SECTION_SOURCE_OUTLINE = "outline"
PDF_SECTION_SOURCE_TOC = "toc"
PDF_SECTION_SOURCE_PAGES = "pages"

PDF_PARSE_STATUS_LABELS = {
    PDF_PARSE_STATUS_PENDING: "待解析",
    PDF_PARSE_STATUS_PROCESSING: "解析中",
    PDF_PARSE_STATUS_READY: "已完成",
    PDF_PARSE_STATUS_FAILED: "解析失败",
}

PDF_SECTION_SOURCE_LABELS = {
    PDF_SECTION_SOURCE_OUTLINE: "PDF 书签",
    PDF_SECTION_SOURCE_TOC: "目录规则识别",
    PDF_SECTION_SOURCE_PAGES: "按页浏览",
}

PDF_MAX_PAGE_COUNT = 600
PDF_MAX_TOTAL_CHARS = 1_200_000
PDF_MAX_EXCERPT_CHARS = 24_000
PDF_TOC_SCAN_PAGES = 8


@dataclass(frozen=True)
class ParsedPdfPage:
    page_number: int
    text: str
    char_count: int


@dataclass(frozen=True)
class ParsedPdfSection:
    title: str
    level: int
    start_page: int
    end_page: int
    sort_index: int
    parent_sort_index: int | None
    source: str


@dataclass(frozen=True)
class ParsedPdfDocument:
    display_title: str
    page_count: int
    total_chars: int
    section_source: str
    pages: tuple[ParsedPdfPage, ...]
    sections: tuple[ParsedPdfSection, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _SectionCandidate:
    level: int
    title: str
    start_page: int


def get_pdf_parse_status_label(status: str) -> str:
    return PDF_PARSE_STATUS_LABELS.get(status, status)


def get_pdf_section_source_label(source: str) -> str:
    return PDF_SECTION_SOURCE_LABELS.get(source, source)


def serialize_pdf_document_row(row: sqlite3.Row | Any) -> dict[str, Any]:
    status = str(row["parse_status"] or PDF_PARSE_STATUS_PENDING)
    source = str(row["section_source"] or PDF_SECTION_SOURCE_PAGES)
    return {
        "id": int(row["id"]),
        "original_file_name": str(row["original_file_name"]),
        "display_title": str(row["display_title"] or Path(str(row["original_file_name"])).stem),
        "parse_status": status,
        "parse_status_label": get_pdf_parse_status_label(status),
        "parse_error": str(row["parse_error"] or ""),
        "parse_warning": str(row["parse_warning"] or ""),
        "section_source": source,
        "section_source_label": get_pdf_section_source_label(source),
        "file_size_bytes": int(row["file_size_bytes"] or 0),
        "page_count": int(row["page_count"] or 0),
        "total_chars": int(row["total_chars"] or 0),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "parsed_at": row["parsed_at"],
    }


def build_pdf_section_tree(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    items: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []

    for row in rows:
        item = {
            "id": int(row["id"]),
            "title": str(row["title"]),
            "level": int(row["level"]),
            "start_page": int(row["start_page"]),
            "end_page": int(row["end_page"]),
            "sort_index": int(row["sort_index"]),
            "source": str(row["source"]),
            "source_label": get_pdf_section_source_label(str(row["source"])),
            "children": [],
        }
        items[item["id"]] = item

        parent_id = row["parent_id"]
        if parent_id is None:
            roots.append(item)
            continue

        parent = items.get(int(parent_id))
        if parent is None:
            roots.append(item)
            continue
        parent["children"].append(item)

    return roots


def normalize_pdf_text(text: str) -> str:
    cleaned = str(text or "").replace("\x00", "")
    cleaned = normalize_extracted_text(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _import_pdfplumber() -> Any:
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - exercised via runtime error path
        raise RuntimeError(
            "当前环境缺少 `pdfplumber` 依赖，无法解析 PDF，请先执行 `pip install -r requirements.txt`。"
        ) from exc
    return pdfplumber


def _build_page_lookup(pdf: Any) -> dict[int, int]:
    page_lookup: dict[int, int] = {}
    for page_number, page in enumerate(getattr(pdf, "pages", []), start=1):
        page_obj = getattr(page, "page_obj", None)
        for attr in ("pageid", "objid"):
            raw_value = getattr(page_obj, attr, None)
            if isinstance(raw_value, int):
                page_lookup[raw_value] = page_number
    return page_lookup


def _lookup_page_number_from_outline_target(target: Any, page_lookup: dict[int, int]) -> int | None:
    try:
        from pdfminer.pdftypes import resolve1
    except Exception:
        return None

    queue = [target]
    visited: set[int] = set()

    while queue:
        current = queue.pop(0)
        marker = id(current)
        if marker in visited:
            continue
        visited.add(marker)

        for attr in ("pageid", "objid"):
            raw_value = getattr(current, attr, None)
            if isinstance(raw_value, int) and raw_value in page_lookup:
                return page_lookup[raw_value]

        if isinstance(current, int) and current in page_lookup:
            return page_lookup[current]

        resolved = resolve1(current)
        if resolved is not current:
            queue.append(resolved)

        if isinstance(current, dict):
            for key in ("D", "Dest", "Page", "P"):
                nested = current.get(key)
                if nested is not None:
                    queue.append(nested)
            continue

        if isinstance(current, (list, tuple)):
            queue.extend(list(current[:3]))

    return None


def _resolve_outline_page_number(pdf: Any, dest: Any, action: Any, page_lookup: dict[int, int]) -> int | None:
    try:
        from pdfminer.pdftypes import resolve1
    except Exception:
        return None

    candidates: list[Any] = []
    if action is not None:
        action_resolved = resolve1(action)
        if isinstance(action_resolved, dict):
            for key in ("D", "Dest"):
                nested = action_resolved.get(key)
                if nested is not None:
                    candidates.append(nested)
    if dest is not None:
        if isinstance(dest, (str, bytes)):
            try:
                candidates.append(pdf.doc.get_dest(dest))
            except Exception:
                candidates.append(dest)
        else:
            candidates.append(dest)

    for candidate in candidates:
        page_number = _lookup_page_number_from_outline_target(candidate, page_lookup)
        if page_number is not None:
            return page_number
    return None


def _normalize_section_title(title: Any) -> str:
    return re.sub(r"\s+", " ", str(title or "")).strip()


def _infer_section_level(title: str) -> int:
    normalized = _normalize_section_title(title)
    dotted_match = re.match(r"^(\d+(?:\.\d+)*)", normalized)
    if dotted_match:
        return dotted_match.group(1).count(".") + 1

    if re.match(r"^第[一二三四五六七八九十百零两0-9]+节", normalized):
        return 2
    if re.match(r"^第[一二三四五六七八九十百零两0-9]+章", normalized):
        return 1
    if re.match(r"^[一二三四五六七八九十]{1,3}[、.]", normalized):
        return 1
    if re.match(r"^[A-Z](?:\.\d+)*\b", normalized):
        return normalized.count(".") + 1
    return 1


def _looks_like_section_title(title: str) -> bool:
    normalized = _normalize_section_title(title)
    if len(normalized) < 2 or len(normalized) > 90:
        return False
    if normalized.lower() in {"目录", "目 录", "contents", "table of contents"}:
        return False
    if re.fullmatch(r"[\d.\-_/ ]+", normalized):
        return False
    return True


def _build_sections_from_candidates(
    candidates: Sequence[_SectionCandidate],
    *,
    page_count: int,
    source: str,
) -> tuple[ParsedPdfSection, ...]:
    if not candidates:
        return ()

    sections: list[ParsedPdfSection] = []
    stack: list[dict[str, int]] = []
    for sort_index, candidate in enumerate(candidates, start=1):
        while stack and stack[-1]["level"] >= candidate.level:
            stack.pop()
        parent_sort_index = stack[-1]["sort_index"] if stack else None
        sections.append(
            ParsedPdfSection(
                title=candidate.title,
                level=max(1, candidate.level),
                start_page=candidate.start_page,
                end_page=candidate.start_page,
                sort_index=sort_index,
                parent_sort_index=parent_sort_index,
                source=source,
            )
        )
        stack.append({"level": max(1, candidate.level), "sort_index": sort_index})

    finalized: list[ParsedPdfSection] = []
    for index, section in enumerate(sections):
        end_page = page_count
        for next_section in sections[index + 1 :]:
            if next_section.level <= section.level:
                end_page = max(section.start_page, next_section.start_page - 1)
                break
        finalized.append(
            ParsedPdfSection(
                title=section.title,
                level=section.level,
                start_page=section.start_page,
                end_page=max(section.start_page, end_page),
                sort_index=section.sort_index,
                parent_sort_index=section.parent_sort_index,
                source=section.source,
            )
        )
    return tuple(finalized)


def extract_outline_sections(pdf: Any) -> tuple[ParsedPdfSection, ...]:
    page_lookup = _build_page_lookup(pdf)
    if not page_lookup:
        return ()

    try:
        outline_items = list(pdf.doc.get_outlines())
    except Exception:
        return ()

    page_count = len(getattr(pdf, "pages", []))
    candidates: list[_SectionCandidate] = []
    seen: set[tuple[str, int]] = set()
    for item in outline_items:
        if not isinstance(item, (list, tuple)) or len(item) < 5:
            continue
        level, title, dest, action, _se = item[:5]
        normalized_title = _normalize_section_title(title)
        if not _looks_like_section_title(normalized_title):
            continue
        page_number = _resolve_outline_page_number(pdf, dest, action, page_lookup)
        if page_number is None or page_number < 1 or page_number > page_count:
            continue
        key = (normalized_title, page_number)
        if key in seen:
            continue
        seen.add(key)
        try:
            resolved_level = max(1, int(level))
        except (TypeError, ValueError):
            resolved_level = 1
        candidates.append(
            _SectionCandidate(
                level=resolved_level,
                title=normalized_title,
                start_page=page_number,
            )
        )

    return _build_sections_from_candidates(
        candidates,
        page_count=page_count,
        source=PDF_SECTION_SOURCE_OUTLINE,
    )


_TOC_LINE_PATTERNS = (
    re.compile(r"^(?P<title>.+?)\s*(?:\.{2,}|…{2,}|·{2,}|-{2,}|_{2,})\s*(?P<page>\d{1,4})$"),
    re.compile(r"^(?P<title>.+?)\s{2,}(?P<page>\d{1,4})$"),
    re.compile(r"^(?P<title>(?:第[一二三四五六七八九十百零两0-9]+[章节篇部卷]|\d+(?:\.\d+){0,3}|[一二三四五六七八九十]{1,3}[、.]).+?)\s+(?P<page>\d{1,4})$"),
)


def detect_sections_from_toc_pages(pages: Sequence[ParsedPdfPage]) -> tuple[ParsedPdfSection, ...]:
    if not pages:
        return ()

    page_count = len(pages)
    scan_pages = pages[: min(PDF_TOC_SCAN_PAGES, page_count)]
    candidates: list[_SectionCandidate] = []
    seen: set[tuple[str, int]] = set()
    for page in scan_pages:
        for raw_line in page.text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            for pattern in _TOC_LINE_PATTERNS:
                match = pattern.match(line)
                if not match:
                    continue
                title = _normalize_section_title(match.group("title"))
                page_text = str(match.group("page") or "").strip()
                if not _looks_like_section_title(title):
                    break
                try:
                    start_page = int(page_text)
                except ValueError:
                    break
                if start_page < 1 or start_page > page_count:
                    break
                key = (title, start_page)
                if key in seen:
                    break
                seen.add(key)
                candidates.append(
                    _SectionCandidate(
                        level=_infer_section_level(title),
                        title=title,
                        start_page=start_page,
                    )
                )
                break

    monotonic_candidates: list[_SectionCandidate] = []
    last_page = 0
    for candidate in candidates:
        if candidate.start_page < last_page:
            continue
        monotonic_candidates.append(candidate)
        last_page = candidate.start_page

    if len(monotonic_candidates) < 2:
        return ()

    return _build_sections_from_candidates(
        monotonic_candidates,
        page_count=page_count,
        source=PDF_SECTION_SOURCE_TOC,
    )


def parse_pdf_document(file_path: Path, *, display_name: str = "") -> ParsedPdfDocument:
    pdfplumber = _import_pdfplumber()
    title = display_name.strip() or Path(file_path).stem

    with pdfplumber.open(str(file_path)) as pdf:
        page_count = len(pdf.pages)
        if page_count <= 0:
            raise ValueError("PDF 没有可读取页面。")
        if page_count > PDF_MAX_PAGE_COUNT:
            raise ValueError(f"PDF 页数过多（{page_count} 页），当前上限为 {PDF_MAX_PAGE_COUNT} 页。")

        pages: list[ParsedPdfPage] = []
        total_chars = 0
        for page_number, page in enumerate(pdf.pages, start=1):
            text = normalize_pdf_text(page.extract_text() or "")
            total_chars += len(text)
            if total_chars > PDF_MAX_TOTAL_CHARS:
                raise ValueError(
                    f"PDF 文本量过大，当前上限为 {PDF_MAX_TOTAL_CHARS} 个字符，请拆分后上传。"
                )
            pages.append(
                ParsedPdfPage(
                    page_number=page_number,
                    text=text,
                    char_count=len(text),
                )
            )

        if not any(page.text for page in pages):
            raise ValueError("未提取到可用文本，当前仅支持文本型 PDF，不支持扫描件 OCR。")

        sections = extract_outline_sections(pdf)
        section_source = PDF_SECTION_SOURCE_OUTLINE
        warnings: list[str] = []
        if not sections:
            sections = detect_sections_from_toc_pages(pages)
            section_source = PDF_SECTION_SOURCE_TOC
        if not sections:
            section_source = PDF_SECTION_SOURCE_PAGES
            warnings.append("未识别到章节结构，已退化为按页浏览。")

    return ParsedPdfDocument(
        display_title=title,
        page_count=page_count,
        total_chars=total_chars,
        section_source=section_source,
        pages=tuple(pages),
        sections=sections,
        warnings=tuple(warnings),
    )


def build_excerpt_text_blocks(
    document_row: sqlite3.Row | Any,
    page_rows: Sequence[sqlite3.Row],
    *,
    mode: str,
    label: str,
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    header_lines = [
        "[PDF 节选]",
        f"文档：{document_row['original_file_name']}",
        f"标题：{document_row['display_title'] or Path(str(document_row['original_file_name'])).stem}",
        f"方式：{'按章节' if mode == 'section' else '按页范围'}",
        f"范围：{label}",
        f"章节来源：{get_pdf_section_source_label(str(document_row['section_source'] or PDF_SECTION_SOURCE_PAGES))}",
    ]
    blocks.append({"type": "meta", "label": "文档信息", "text": "\n".join(header_lines)})

    remaining_chars = PDF_MAX_EXCERPT_CHARS
    truncated = False
    start_page: int | None = None
    end_page: int | None = None

    for row in page_rows:
        page_number = int(row["page_number"])
        page_text = str(row["text"] or "").strip()
        if not page_text:
            continue
        if start_page is None:
            start_page = page_number
        end_page = page_number

        current_text = page_text
        if len(current_text) > remaining_chars:
            current_text = current_text[:remaining_chars].rstrip()
            truncated = True
        remaining_chars -= len(current_text)
        if current_text:
            blocks.append(
                {
                    "type": "page",
                    "label": f"第 {page_number} 页",
                    "page_number": page_number,
                    "text": current_text,
                }
            )
        if remaining_chars <= 0:
            truncated = True
            break

    if len(blocks) <= 1:
        raise ValueError("所选范围没有可发送的文本内容。")

    text_parts = [str(block["text"]) for block in blocks[:1]]
    for block in blocks[1:]:
        text_parts.append(f"[{block['label']}]\n{block['text']}")
    warning = ""
    if truncated:
        warning = f"节选内容超过 {PDF_MAX_EXCERPT_CHARS} 个字符，已自动截断。"
        text_parts.append(f"[提示]\n{warning}")

    excerpt_text = "\n\n".join(text_parts).strip()
    return {
        "mode": mode,
        "label": label,
        "blocks": blocks,
        "text": excerpt_text,
        "warning": warning,
        "char_count": len(excerpt_text),
        "start_page": start_page,
        "end_page": end_page,
    }
