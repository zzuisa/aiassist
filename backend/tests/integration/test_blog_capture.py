"""Capture durability + URL extraction failure/retry (US1, T029).

Proves the core US1 guarantee: the raw source and first revision are saved before
any extraction runs, the authored Post text is never overwritten by extraction,
URL failures are recorded without data loss, and a failed source can be retried
exactly once into a fresh attempt.
"""

from __future__ import annotations

import pytest

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration]


@pytest.fixture
def user_id(make_user):
    return make_user().id


@requires_db
def test_capture_saves_source_and_first_revision_before_processing(db_session, user_id):
    from app.models.posts import PostRevision
    from app.modules.posts import capture_service

    post, src, _job, _warnings = capture_service.capture_quick(
        db_session, user_id, content="raw material"
    )
    db_session.commit()

    # Raw content is durable immediately.
    assert src.original_text == "raw material"
    assert src.status == "completed"
    # A first 'capture' revision exists and is current.
    rev = db_session.get(PostRevision, post.current_revision_id)
    assert rev is not None
    assert rev.source == "capture"
    assert rev.applied_at is not None


@requires_db
def test_url_capture_saves_pending_before_network(db_session, user_id):
    from app.modules.posts import capture_service

    post, src, job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/a", note="note"
    )
    db_session.commit()

    assert post.content_status == "pending_parse"
    assert src.status == "pending"
    assert src.original_url == "https://example.com/a"
    assert job is not None and job.job_type == "blog.parse"
    assert src.async_job_id == job.id


@requires_db
def test_bilibili_capture_selects_radio_job_without_affecting_webpages(db_session, user_id):
    from app.modules.posts import capture_service

    post, source, job, _ = capture_service.capture_url(
        db_session,
        user_id,
        url="https://www.bilibili.com/video/BV1abc123",
        note="稍后整理",
    )
    db_session.commit()

    assert job.job_type == "blog.bilibili_import"
    assert source.metadata_json["url_type"] == "bilibili"
    assert source.external_system == "radio"
    assert post.markdown == "<https://www.bilibili.com/video/BV1abc123>"

    _post, webpage_source, webpage_job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/article"
    )
    assert webpage_job.job_type == "blog.parse"
    assert webpage_source.external_system is None


@requires_db
def test_bilibili_radio_success_updates_title_body_and_external_id(
    db_session, user_id, monkeypatch
):
    import app.services.radio as radio_service
    from app.models.blog import PostSource
    from app.models.foundation import AsyncJob
    from app.models.posts import Post
    from app.modules.posts import capture_service
    from app.services.radio.client import RadioTask
    from app.workers.tasks import blog as blog_task

    post, source, job, _ = capture_service.capture_url(
        db_session, user_id, url="https://b23.tv/abc123"
    )
    db_session.commit()

    class FakeRadio:
        def submit_bilibili_transcription(self, url):
            assert url == "https://b23.tv/abc123"
            return "radio-task-1"

        def get_task(self, task_id):
            assert task_id == "radio-task-1"
            return RadioTask(
                id=task_id,
                status="success",
                progress=100,
                message="完成",
                error=None,
                result={
                    "video_info": {"title": "B站视频标题", "bvid": "BV1abc"},
                    "text": "完整转写正文",
                    "transcript_id": "stt-1",
                },
            )

    monkeypatch.setattr(radio_service, "get_radio_client", lambda: FakeRadio())
    assert blog_task.import_bilibili_source(source.id) == "polling"
    assert blog_task.import_bilibili_source(source.id) == "completed"

    db_session.expire_all()
    updated_post = db_session.get(Post, post.id)
    updated_source = db_session.get(PostSource, source.id)
    updated_job = db_session.get(AsyncJob, job.id)
    assert updated_post.title == "B站视频标题"
    assert updated_post.markdown == "完整转写正文"
    assert updated_source.external_record_id == "stt-1"
    assert updated_job.status == "completed"


@requires_db
def test_bilibili_radio_unavailable_is_actionable(db_session, user_id, monkeypatch):
    import app.services.radio as radio_service
    from app.models.blog import PostSource
    from app.models.foundation import AsyncJob
    from app.modules.posts import capture_service
    from app.services.radio.client import RadioServiceError
    from app.workers.tasks import blog as blog_task

    _post, source, job, _ = capture_service.capture_url(
        db_session, user_id, url="https://b23.tv/abc123"
    )
    db_session.commit()

    class DownRadio:
        def submit_bilibili_transcription(self, url):
            raise RadioServiceError(
                "RADIO_SERVICE_UNAVAILABLE",
                "B站音视频处理服务当前不可用，请稍后重试。",
                diagnostic="connect_timeout",
            )

    monkeypatch.setattr(radio_service, "get_radio_client", lambda: DownRadio())
    assert blog_task.import_bilibili_source(source.id) == "failed"
    db_session.expire_all()
    failed_source = db_session.get(PostSource, source.id)
    failed_job = db_session.get(AsyncJob, job.id)
    assert failed_source.error_code == "RADIO_SERVICE_UNAVAILABLE"
    assert failed_job.error_code == "RADIO_SERVICE_UNAVAILABLE"
    assert failed_job.error_message == "B站音视频处理服务当前不可用，请稍后重试。"


@requires_db
def test_extraction_never_overwrites_authored_post(db_session, user_id, monkeypatch):
    from app.models.blog import PostSource
    from app.models.posts import Post
    from app.modules.posts import capture_service, url_extractor
    from app.workers.tasks import blog as blog_task

    post, src, _job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/a", note="my own words"
    )
    db_session.commit()
    authored_markdown = post.markdown

    # Simulate a successful fetch + extraction with different body text.
    monkeypatch.setattr(
        url_extractor,
        "fetch_url",
        lambda url, **kw: url_extractor.FetchResult(
            final_url=url,
            status_code=200,
            content_type="text/html",
            text="<html><body><article>extracted body</article></body></html>",
        ),
    )
    monkeypatch.setattr(
        url_extractor,
        "extract_article",
        lambda html, url: {
            "title": "T",
            "text": "extracted body",
            "markdown": "extracted body",
            "author": None,
            "site": None,
        },
    )

    result = blog_task.extract_source(src.id)
    assert result == "completed"

    db_session.expire_all()
    refreshed_post = db_session.get(Post, post.id)
    refreshed_src = db_session.get(PostSource, src.id)
    # Post body is untouched; only the source carries the extraction.
    assert refreshed_post.markdown == authored_markdown
    assert refreshed_src.normalized_markdown == "extracted body"
    assert refreshed_src.status == "completed"


@requires_db
def test_extraction_advances_post_and_completes_parse_job(db_session, user_id, monkeypatch):
    """Regression: a URL import must leave pending_parse, not get stuck ('处理失败')."""
    from app.models.foundation import AsyncJob
    from app.models.posts import Post
    from app.modules.posts import capture_service, url_extractor
    from app.workers.tasks import blog as blog_task

    post, src, job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/article"
    )
    db_session.commit()
    assert post.content_status == "pending_parse"
    assert job.status in ("pending", "queued")

    monkeypatch.setattr(
        url_extractor,
        "fetch_url",
        lambda url, **kw: url_extractor.FetchResult(
            final_url=url,
            status_code=200,
            content_type="text/html",
            text="<html><body><article>正文内容</article></body></html>",
        ),
    )
    monkeypatch.setattr(
        url_extractor,
        "extract_article",
        lambda html, url: {
            "title": "抓取到的标题",
            "text": "正文内容",
            "markdown": "正文内容",
            "author": None,
            "site": None,
        },
    )

    assert blog_task.extract_source(src.id) == "completed"
    db_session.expire_all()

    p = db_session.get(Post, post.id)
    j = db_session.get(AsyncJob, job.id)
    # The article moved out of the transient holding state and the job is done.
    assert p.content_status == "triage"
    assert p.title == "抓取到的标题"  # raw-URL title replaced by the extracted one
    assert p.markdown == "正文内容"  # placeholder body filled from the extraction
    assert j.status == "completed"


@requires_db
def test_failed_extraction_advances_to_triage_with_failed_job(db_session, user_id, monkeypatch):
    from app.models.foundation import AsyncJob
    from app.models.posts import Post
    from app.modules.posts import capture_service, url_extractor
    from app.workers.tasks import blog as blog_task

    post, src, job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/x"
    )
    db_session.commit()

    monkeypatch.setattr(
        url_extractor,
        "fetch_url",
        lambda url, **kw: (_ for _ in ()).throw(
            url_extractor.UrlSecurityError("timed out", code="timeout")
        ),
    )
    assert blog_task.extract_source(src.id) == "failed"
    db_session.expire_all()

    p = db_session.get(Post, post.id)
    j = db_session.get(AsyncJob, job.id)
    assert p.content_status == "triage"  # visible + retryable, never stuck
    assert j.status == "failed" and j.error_retryable is True


@requires_db
def test_url_failure_is_recorded_and_retryable_once(db_session, user_id, monkeypatch):
    from app.models.blog import PostSource
    from app.modules.posts import capture_service, url_extractor
    from app.workers.tasks import blog as blog_task

    _post, src, _job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/a"
    )
    db_session.commit()

    def _boom(url, **kw):
        raise url_extractor.UrlSecurityError("timed out", code="timeout")

    monkeypatch.setattr(url_extractor, "fetch_url", _boom)

    assert blog_task.extract_source(src.id) == "failed"
    db_session.expire_all()
    failed = db_session.get(PostSource, src.id)
    assert failed.status == "failed"
    assert failed.error_code == "timeout"
    attempts_before = failed.fetch_attempt_count

    # Retry arms a fresh attempt.
    job = capture_service.retry_source(db_session, user_id, src.id)
    db_session.commit()
    db_session.expire_all()
    retried = db_session.get(PostSource, src.id)
    assert retried.status == "pending"
    assert retried.error_code is None
    assert retried.fetch_attempt_count == attempts_before + 1
    assert job.job_type == "blog.parse"


@requires_db
def test_retry_rejected_for_non_failed_source(db_session, user_id):
    from app.core.errors import ConflictError
    from app.modules.posts import capture_service

    _post, src, _job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/a"
    )
    db_session.commit()
    # Still pending (never failed) — retry must be refused.
    with pytest.raises(ConflictError):
        capture_service.retry_source(db_session, user_id, src.id)


@requires_db
def test_partial_extraction_marks_partial(db_session, user_id, monkeypatch):
    from app.models.blog import PostSource
    from app.modules.posts import capture_service, url_extractor
    from app.workers.tasks import blog as blog_task

    _post, src, _job, _ = capture_service.capture_url(
        db_session, user_id, url="https://example.com/a"
    )
    db_session.commit()

    monkeypatch.setattr(
        url_extractor,
        "fetch_url",
        lambda url, **kw: url_extractor.FetchResult(
            final_url=url,
            status_code=200,
            content_type="text/html",
            text="<html></html>",
            truncated=True,
        ),
    )
    monkeypatch.setattr(
        url_extractor,
        "extract_article",
        lambda html, url: {
            "title": None,
            "text": "some",
            "markdown": "some",
            "author": None,
            "site": None,
        },
    )
    assert blog_task.extract_source(src.id) == "partial"
    db_session.expire_all()
    assert db_session.get(PostSource, src.id).error_code == "truncated"
