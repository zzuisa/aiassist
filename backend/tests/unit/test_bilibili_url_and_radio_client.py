from __future__ import annotations

import httpx
import pytest
from app.modules.posts.url_types import UrlType, detect_url_type
from app.services.radio.client import RADIO_UNAVAILABLE, RadioClient, RadioServiceError


def test_bilibili_worker_keeps_long_polling_retry_budget(monkeypatch):
    from app.workers.tasks import blog

    retry_options = {}

    def fake_retry(**kwargs):
        retry_options.update(kwargs)
        raise RuntimeError("retry scheduled")

    monkeypatch.setattr(blog, "import_bilibili_source", lambda _source_id: "polling")
    monkeypatch.setattr(blog.import_bilibili, "retry", fake_retry)

    with pytest.raises(RuntimeError, match="retry scheduled"):
        blog.import_bilibili.run("00000000-0000-0000-0000-000000000001")

    assert retry_options["max_retries"] == 8640


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bilibili.com/video/BV1abc123",
        "https://bilibili.com/video/BV1abc123/",
        "https://b23.tv/abc123",
        "http://b23.tv/abc123",
    ],
)
def test_detects_supported_bilibili_urls(url):
    assert detect_url_type(url) is UrlType.bilibili


def test_normal_webpage_and_invalid_url_are_not_bilibili():
    assert detect_url_type("https://example.com/article") is UrlType.webpage
    assert detect_url_type("https://evil-bilibili.com/video/BV1abc") is UrlType.webpage
    assert detect_url_type("not a url") is UrlType.unsupported
    assert detect_url_type("ftp://b23.tv/a") is UrlType.unsupported


def _client(handler) -> RadioClient:
    return RadioClient(
        base_url="https://radio.example.test",
        password="test-password",
        connect_timeout=1,
        read_timeout=2,
        transport=httpx.MockTransport(handler),
    )


def test_radio_task_submit_and_result_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/verify":
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/api/tasks/speech2text/bilibili":
            return httpx.Response(200, json={"ok": True, "task_id": "radio-task-1"})
        return httpx.Response(
            200,
            json={
                "ok": True,
                "task": {
                    "id": "radio-task-1",
                    "status": "success",
                    "progress": 100,
                    "message": "完成",
                    "error": None,
                    "result": {
                        "video_info": {"title": "视频标题", "bvid": "BV1abc"},
                        "text": "完整转写",
                        "transcript_id": "stt-1",
                    },
                },
            },
        )

    client = _client(handler)
    assert client.submit_bilibili_transcription("https://b23.tv/a") == "radio-task-1"
    task = client.get_task("radio-task-1")
    assert task.status == "success"
    assert task.result and task.result["transcript_id"] == "stt-1"


def test_radio_article_optimization_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/verify":
            return httpx.Response(200, json={"ok": True})
        assert request.url.path == "/api/text/optimize"
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={"ok": True, "optimized_text": "优化后的 Markdown"},
        )

    optimized = _client(handler).optimize_text("原文", instruction="轻量润色")
    assert optimized == "优化后的 Markdown"


def test_radio_article_optimization_rejects_empty_response():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/verify":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"ok": True, "optimized_text": ""})

    with pytest.raises(RadioServiceError) as caught:
        _client(handler).optimize_text("原文")
    assert caught.value.code == RADIO_UNAVAILABLE
    assert caught.value.diagnostic == "optimize_invalid_response"


@pytest.mark.parametrize(
    ("failure", "diagnostic"),
    [
        (httpx.ConnectError("down"), "connect_error"),
        (httpx.ConnectTimeout("slow connect"), "connect_timeout"),
        (httpx.ReadTimeout("slow read"), "read_timeout"),
    ],
)
def test_radio_transport_failures_have_stable_code(failure, diagnostic):
    def handler(_: httpx.Request) -> httpx.Response:
        raise failure

    with pytest.raises(RadioServiceError) as caught:
        _client(handler).submit_bilibili_transcription("https://b23.tv/a")
    assert caught.value.code == RADIO_UNAVAILABLE
    assert caught.value.diagnostic == diagnostic
    assert caught.value.public_message == "B站音视频处理服务当前不可用，请稍后重试。"


def test_radio_500_and_invalid_response_are_unavailable():
    def server_error(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/verify":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(500, json={"detail": "internal"})

    with pytest.raises(RadioServiceError) as caught:
        _client(server_error).submit_bilibili_transcription("https://b23.tv/a")
    assert caught.value.code == RADIO_UNAVAILABLE
    assert caught.value.diagnostic == "http_500"

    def invalid(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/verify":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"ok": True})

    with pytest.raises(RadioServiceError) as caught:
        _client(invalid).submit_bilibili_transcription("https://b23.tv/a")
    assert caught.value.diagnostic == "submit_invalid_response"


def test_radio_records_require_real_pagination_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/verify":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(
            200,
            json={
                "ok": True,
                "items": [{"id": "stt-1", "text": "body"}],
                "total": 2,
                "limit": 1,
                "offset": 0,
                "has_more": True,
                "next_offset": 1,
            },
        )

    page = _client(handler).list_transcripts(limit=1, offset=0)
    assert page.total == 2
    assert page.next_offset == 1
