from __future__ import annotations

from gtpweb.assistant_actions import parse_assistant_action



def test_parse_assistant_action_supports_stringified_action_input() -> None:
    action = parse_assistant_action(
        '{'
        '"action":"dalle.text2im",'
        '"action_input":"{\\"prompt\\":\\"一只白猫\\"}",'
        '"thought":"准备生成图片"'
        '}'
    )

    assert action is not None
    assert action.name == "dalle.text2im"
    assert action.action_input == {"prompt": "一只白猫"}
    assert action.thought == "准备生成图片"



def test_parse_assistant_action_supports_json_code_fence() -> None:
    action = parse_assistant_action(
        "```json\n{\"action\":\"dalle.text2im\",\"action_input\":{\"prompt\":\"一只黑猫\"}}\n```"
    )

    assert action is not None
    assert action.action_input == {"prompt": "一只黑猫"}
