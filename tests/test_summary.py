# -*- coding: utf-8 -*-
"""摘要服务测试。"""
from __future__ import annotations

import json

import httpx

from cyberpunk_mod_manager.services.summary import (
    _extract_message_content,
    _parse_chat_response,
    _parse_sse_response,
    fallback_summary,
    parse_llm_json_from_response,
    parse_llm_json_object,
)


def test_fallback_summary() -> None:
    text = fallback_summary("<p>Shared runtime for CET mods.</p>", name="0-Engine")
    assert text


def test_parse_sse_response() -> None:
    sse = (
        'data: {"choices":[{"delta":{"content":"赛博"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"朋克框架"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    data = _parse_sse_response(sse)
    assert _extract_message_content(data) == "赛博朋克框架"


def test_parse_chat_response_json() -> None:
    body = json.dumps(
        {
            "choices": [
                {"message": {"content": "CET 模组运行时框架", "role": "assistant"}}
            ]
        }
    )
    resp = httpx.Response(200, headers={"content-type": "application/json"}, content=body)
    data = _parse_chat_response(resp)
    assert _extract_message_content(data) == "CET 模组运行时框架"


def test_extract_from_reasoning_content() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "reasoning_content": "这是推理过程。最终答案是一句简介。",
                }
            }
        ]
    }
    text = _extract_message_content(data)
    assert "推理" in text


def test_parse_llm_json_object_from_markdown_fence() -> None:
    text = (
        "分析如下：\n"
        '```json\n'
        '{"summary":"需要补依赖","risks":["冲突"],"recommendations":[]}\n'
        "```"
    )
    parsed = parse_llm_json_object(text)
    assert parsed["summary"] == "需要补依赖"
    assert parsed["risks"] == ["冲突"]


def test_parse_llm_json_from_reasoning_response() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "reasoning_content": (
                        '{"summary":"优先补全33个依赖不全模组",'
                        '"risks":[],"recommendations":[{"action":"install_deps","mod_id":1,"reason":"缺依赖"}]}'
                    ),
                }
            }
        ]
    }
    parsed = parse_llm_json_from_response(data)
    assert "依赖不全" in parsed["summary"]
    assert parsed["recommendations"][0]["mod_id"] == 1
