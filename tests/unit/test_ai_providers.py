from __future__ import annotations

from gtpweb.ai_providers import (
    build_google_contents,
    build_model_options,
    normalize_model_selection,
    resolve_model_option,
)


def test_resolve_model_option_supports_legacy_raw_model_name() -> None:
    options = build_model_options(["gpt-4o-mini"], ["gemini-2.0-flash"])

    resolved = resolve_model_option("gpt-4o-mini", options)

    assert resolved is not None
    assert resolved.id == "openai:gpt-4o-mini"
    assert normalize_model_selection("gpt-4o-mini", options, fallback_to_first=True) == "openai:gpt-4o-mini"


def test_build_google_contents_converts_openai_style_parts() -> None:
    contents = build_google_contents(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看看图片"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,aGVsbG8="},
                    },
                ],
            },
            {"role": "assistant", "content": "收到"},
        ]
    )

    assert contents == [
        {
            "role": "user",
            "parts": [
                {"text": "看看图片"},
                {"inline_data": {"mime_type": "image/png", "data": "aGVsbG8="}},
            ],
        },
        {
            "role": "model",
            "parts": [{"text": "收到"}],
        },
    ]
