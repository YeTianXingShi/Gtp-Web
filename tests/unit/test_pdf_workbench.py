from __future__ import annotations

from gtpweb.pdf_workbench import (
    PDF_SECTION_SOURCE_TOC,
    ParsedPdfPage,
    build_excerpt_text_blocks,
    detect_sections_from_toc_pages,
)


def test_detect_sections_from_toc_pages_builds_hierarchy_and_ranges():
    pages = [
        ParsedPdfPage(
            page_number=1,
            text=(
                "目录\n"
                "第一章 绪论 ........ 1\n"
                "1.1 背景与目标 ........ 2\n"
                "第二章 实现方案 ........ 5\n"
            ),
            char_count=40,
        ),
        *[
            ParsedPdfPage(page_number=index, text=f"第 {index} 页正文", char_count=8)
            for index in range(2, 7)
        ],
    ]

    sections = detect_sections_from_toc_pages(pages)

    assert len(sections) == 3
    assert sections[0].title == "第一章 绪论"
    assert sections[0].start_page == 1
    assert sections[0].end_page == 4
    assert sections[0].source == PDF_SECTION_SOURCE_TOC
    assert sections[1].title == "1.1 背景与目标"
    assert sections[1].level == 2
    assert sections[1].parent_sort_index == 1
    assert sections[2].title == "第二章 实现方案"
    assert sections[2].start_page == 5
    assert sections[2].end_page == 6


def test_build_excerpt_text_blocks_includes_metadata_and_truncation_notice():
    document_row = {
        "original_file_name": "manual.pdf",
        "display_title": "产品手册",
        "section_source": "outline",
    }
    page_rows = [
        {"page_number": 3, "text": "A" * 20000, "char_count": 20000},
        {"page_number": 4, "text": "B" * 20000, "char_count": 20000},
    ]

    excerpt = build_excerpt_text_blocks(
        document_row,
        page_rows,
        mode="page_range",
        label="第 3 - 4 页",
    )

    assert excerpt["mode"] == "page_range"
    assert excerpt["start_page"] == 3
    assert excerpt["end_page"] == 4
    assert excerpt["blocks"][0]["text"].startswith("[PDF 节选]")
    assert excerpt["warning"]
    assert "产品手册" in excerpt["text"]
    assert "第 3 页" in excerpt["text"]
    assert "[提示]" in excerpt["text"]
