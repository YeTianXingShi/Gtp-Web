from __future__ import annotations

from gtpweb.config import parse_model_catalog_text


def test_parse_model_catalog_supports_model_level_enabled_flags() -> None:
    catalog = parse_model_catalog_text(
        '{\n'
        '  "openai": {\n'
        '    "image_model": "",\n'
        '    "defaults": {"reasoning": {"enabled": true, "effort": "high", "summary": "auto"}},\n'
        '    "models": [\n'
        '      {"name": "gpt-5", "reasoning": {"enabled": false}},\n'
        '      {"name": "gpt-5-mini", "reasoning": {"enabled": true, "summary": "concise"}}\n'
        '    ]\n'
        '  },\n'
        '  "google": {\n'
        '    "image_model": "",\n'
        '    "defaults": {"thinking": false},\n'
        '    "models": [\n'
        '      {"name": "gemini-2.5-pro", "thinking": {"include_thoughts": false, "level": "medium"}}\n'
        '    ]\n'
        '  }\n'
        '}\n'
    )

    openai_disabled = catalog.openai.models[0].openai_reasoning
    assert openai_disabled is not None
    assert openai_disabled.enabled is False
    assert openai_disabled.effort == "high"
    assert openai_disabled.summary == "auto"

    openai_enabled = catalog.openai.models[1].openai_reasoning
    assert openai_enabled is not None
    assert openai_enabled.enabled is True
    assert openai_enabled.effort == "high"
    assert openai_enabled.summary == "concise"

    google_enabled = catalog.google.models[0].google_thinking
    assert google_enabled is not None
    assert google_enabled.enabled is True
    assert google_enabled.include_thoughts is False
    assert google_enabled.level == "medium"


def test_parse_model_catalog_allows_clearing_inherited_google_budget() -> None:
    catalog = parse_model_catalog_text(
        '{\n'
        '  "openai": {"image_model": "", "models": []},\n'
        '  "google": {\n'
        '    "image_model": "",\n'
        '    "defaults": {"thinking": {"enabled": true, "budget": 1024}},\n'
        '    "models": [\n'
        '      {"name": "gemini-2.5-pro", "thinking": {"budget": null, "level": "high"}}\n'
        '    ]\n'
        '  }\n'
        '}\n'
    )

    thinking = catalog.google.models[0].google_thinking
    assert thinking is not None
    assert thinking.enabled is True
    assert thinking.budget is None
    assert thinking.level == "high"

