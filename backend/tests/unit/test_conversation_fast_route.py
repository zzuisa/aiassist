"""Pure-conversation fast-path classification: greeting/thanks/goodbye/help,
and the mixed greeting-plus-task boundary that must NOT be claimed."""

from __future__ import annotations

import pytest
from app.modules.agent.conversation_router import FastPathKind, classify_fast_path

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    "text",
    ["hi", "Hi", "hello", "hey", "嗨", "你好", "您好", "早上好", "在吗", "hi!", "你好。", "  嗨  "],
)
def test_classifies_pure_greetings(text: str) -> None:
    assert classify_fast_path(text) is FastPathKind.greeting


@pytest.mark.parametrize("text", ["thanks", "thank you", "谢谢", "谢谢你", "多谢", "感谢", "thx!"])
def test_classifies_pure_thanks(text: str) -> None:
    assert classify_fast_path(text) is FastPathKind.thanks


@pytest.mark.parametrize("text", ["bye", "goodbye", "再见", "拜拜", "晚安", "see you"])
def test_classifies_pure_goodbye(text: str) -> None:
    assert classify_fast_path(text) is FastPathKind.goodbye


@pytest.mark.parametrize(
    "text",
    [
        "你能做什么",
        "你能干什么",
        "你有什么功能",
        "what can you do",
        "What can you do?",
        "能做什么",
    ],
)
def test_classifies_capability_help(text: str) -> None:
    assert classify_fast_path(text) is FastPathKind.capability_help


@pytest.mark.parametrize(
    "text",
    [
        "嗨，帮我看文章",
        "你好，把最近的文章标签整理一下",
        "hi, please list my recent posts",
        "谢谢，另外帮我查一下日历",
        "你好",  # sanity check the boundary is exact, mutated below
    ],
)
def test_mixed_greeting_and_task_is_not_fast_path(text: str) -> None:
    if text == "你好":
        # This one IS pure and must classify — guards the parametrize list
        # itself from silently degenerating into "everything is rejected".
        assert classify_fast_path(text) is FastPathKind.greeting
        return
    assert classify_fast_path(text) is None


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_blank_text_is_not_fast_path(text: str) -> None:
    assert classify_fast_path(text) is None


def test_unrelated_task_text_is_not_fast_path() -> None:
    assert classify_fast_path("帮我看看最近写了什么") is None
    assert classify_fast_path("请把这些文章的标签保存一下") is None
