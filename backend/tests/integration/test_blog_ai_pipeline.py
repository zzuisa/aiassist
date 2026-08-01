"""AI optimization pipeline: resolution, duplicates, stages, candidates (US3, T064).

Drives the worker with an injected gateway so outputs are deterministic. Asserts
the core US3 guarantees: the current article is never mutated, only valid/partial
candidates persist, malformed/timeout outputs fail without side effects, and an
exact-duplicate submission reuses the existing Job.
"""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _valid_skill_config(field_policies: dict | None = None) -> dict:
    return {
        "schema_version": "blog-skill-config.v1",
        "applicable_content_classes": ["technical", "essay"],
        "applicable_content_type_ids": [],
        "processing_goal": "improve clarity",
        "content_rules": [],
        "title_rules": [],
        "summary_rules": [],
        "body_structure": [],
        "taxonomy_rules": [],
        "keyword_rules": [],
        "prohibitions": ["do not invent facts"],
        "field_policies": field_policies or {"title": "allow_overwrite", "summary": "allow_overwrite"},
        "output_fields": ["title", "summary", "markdown"],
        "output_schema": "blog-optimization.v1",
        "validation_rules": [],
        "recommended_model": "test-model",
        "max_content_chars": 200000,
        "long_content_strategy": "reject",
    }


def _make_skill(session, user_id, field_policies=None):
    from app.models.blog import BlogSkill, BlogSkillDefault, BlogSkillVersion

    skill = BlogSkill(id=uuid.uuid4(), user_id=user_id, name="默认技能", enabled=True)
    session.add(skill)
    session.flush()
    version = BlogSkillVersion(
        id=uuid.uuid4(), user_id=user_id, skill_id=skill.id, version_number=1,
        config_json=_valid_skill_config(field_policies), schema_version="blog-skill-config.v1",
        recommended_model="test-model", max_content_chars=200000, long_content_strategy="reject",
    )
    session.add(version)
    session.flush()
    skill.current_version_id = version.id
    session.add(BlogSkillDefault(
        id=uuid.uuid4(), user_id=user_id, scope_type="global", scope_key="*", skill_id=skill.id,
    ))
    session.flush()
    return skill, version


def _opt(title="新标题", summary="新摘要", markdown="正文", **over):
    from app.services.llm.schemas import BlogOptimizationV1

    data = {
        "schema_version": "blog-optimization.v1",
        "title": title, "subtitle": None, "summary": summary, "markdown": markdown,
        "content_class_suggestion": None, "content_type_suggestion": None,
        "category_suggestions": [], "tag_suggestions": [], "keyword_suggestions": [],
        "occurred_at": None, "location": None, "project": None, "source_summary": None,
        "structured_fields": {}, "related_post_suggestions": [], "claims": [], "warnings": [],
    }
    data.update(over)
    return BlogOptimizationV1.model_validate(data)


class _FakeGateway:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def structured(self, request):
        if self._error is not None:
            raise self._error
        return self._result


def _inject_gateway(monkeypatch, gateway):
    import app.services.llm.gateway as gw
    monkeypatch.setattr(gw, "get_llm_gateway", lambda: gateway)


@pytest.fixture
def user_id(make_user):
    return make_user().id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@requires_db
def test_submit_resolves_skill_and_queues(db_session, user_id):
    from app.models.posts import Post
    from app.modules.posts import ai_service, service

    _make_skill(db_session, user_id)
    post = service.create_post(db_session, user_id, title="t", markdown="hello world")
    db_session.commit()

    job, run, dup = ai_service.submit_optimization(
        db_session, user_id, post.id, post_version=post.version,
        optimization_type="full", provider_key="aiassist",
    )
    db_session.commit()
    assert dup is False
    assert job.job_type == "blog.optimize"
    assert run.skill_version_id is not None
    assert run.provider_key == "aiassist"
    assert run.model_key == "test-model"
    assert job.status == "queued"
    assert job.current_step == "等待执行"
    assert job.result_json["context"] == {
        "post_id": str(post.id),
        "post_title": "t",
        "provider_key": "aiassist",
        "optimization_type": "full",
        "scope": "all",
    }
    p = db_session.get(Post, post.id)
    assert p.content_status == "ai_queued"


@requires_db
def test_submit_uses_user_default_provider(db_session, user_id):
    from app.modules.posts import ai_service, service, settings_service

    _make_skill(db_session, user_id)
    post = service.create_post(db_session, user_id, title="t", markdown="body")
    db_session.commit()

    _job, radio_run, _ = ai_service.submit_optimization(
        db_session,
        user_id,
        post.id,
        post_version=post.version,
        optimization_type="language",
    )
    assert radio_run.provider_key == "radio"
    assert radio_run.model_key == "radio-gemini"

    radio_run.outcome = "cancelled"
    settings_service.set_default_ai_provider(db_session, user_id, "aiassist")
    db_session.commit()
    _job, aiassist_run, _ = ai_service.submit_optimization(
        db_session,
        user_id,
        post.id,
        post_version=post.version,
        optimization_type="language",
    )
    assert aiassist_run.provider_key == "aiassist"
    assert aiassist_run.model_key == "test-model"


@requires_db
def test_duplicate_submission_reuses_job(db_session, user_id):
    from app.modules.posts import ai_service, service

    _make_skill(db_session, user_id)
    post = service.create_post(db_session, user_id, title="t", markdown="body")
    db_session.commit()

    job1, run1, _ = ai_service.submit_optimization(
        db_session, user_id, post.id, post_version=post.version,
        optimization_type="full", provider_key="aiassist",
    )
    db_session.commit()
    job2, run2, dup = ai_service.submit_optimization(
        db_session, user_id, post.id, post_version=post.version,
        optimization_type="full", provider_key="aiassist",
    )
    db_session.commit()
    assert dup is True
    assert job2.id == job1.id
    assert run2.id == run1.id


@requires_db
def test_valid_run_saves_candidate_without_touching_article(db_session, user_id, monkeypatch):
    from app.models.blog import PostAICandidate, PostAIRun
    from app.models.foundation import AsyncJob
    from app.models.posts import Post
    from app.modules.posts import ai_service, service
    from app.workers.tasks import blog as blog_task

    _make_skill(db_session, user_id)
    post = service.create_post(db_session, user_id, title="原标题", markdown="原正文 100 元")
    db_session.commit()
    original_markdown = post.markdown

    _job, run, _ = ai_service.submit_optimization(
        db_session, user_id, post.id, post_version=post.version,
        optimization_type="full", provider_key="aiassist",
    )
    db_session.commit()

    _inject_gateway(monkeypatch, _FakeGateway(result=_opt(markdown="原正文 100 元")))
    assert blog_task.optimize_run(run.id, "all", [], None) == "complete"

    db_session.expire_all()
    p = db_session.get(Post, post.id)
    assert p.markdown == original_markdown  # article is never mutated
    assert p.content_status == "ai_review"
    cand = db_session.scalar(
        __import__("sqlalchemy").select(PostAICandidate).where(PostAICandidate.ai_run_id == run.id)
    )
    assert cand is not None and cand.status == "pending"
    finished = db_session.get(PostAIRun, run.id)
    assert finished.outcome == "complete"
    job = db_session.get(AsyncJob, run.async_job_id)
    assert job.status == "waiting_user"
    assert job.result_json["context"]["post_title"] == "原标题"
    assert job.result_json["context"]["provider_key"] == "aiassist"

    # These durable frames are committed as independent worker checkpoints,
    # allowing SSE clients to render progress before the model call completes.
    from app.models.foundation import AsyncJobEvent
    events = list(db_session.scalars(
        __import__("sqlalchemy").select(AsyncJobEvent)
        .where(AsyncJobEvent.job_id == job.id)
        .order_by(AsyncJobEvent.id)
    ))
    steps = [event.payload_json.get("current_step") for event in events]
    assert "正在准备文章" in steps
    assert "正在分析内容" in steps
    assert "AI Assist 正在生成优化内容" in steps
    assert "已收到结果，正在检查" in steps
    assert "正在校验格式与受保护内容" in steps
    assert "正在生成读者示意图" in steps
    assert "正在保存优化候选" in steps


@requires_db
def test_radio_provider_saves_review_candidate(db_session, user_id, monkeypatch):
    from app.models.blog import PostAICandidate
    from app.models.posts import Post, PostRevision
    from app.modules.posts import ai_service, service
    from app.workers.tasks import blog as blog_task
    from sqlalchemy import select

    class FakeRadio:
        def optimize_text(self, text, *, instruction=None):
            assert text == "原始正文。"
            assert instruction == "语句更通顺"
            return "优化后的正文。"

    _make_skill(db_session, user_id)
    post = service.create_post(db_session, user_id, title="标题", markdown="原始正文。")
    db_session.commit()
    _job, run, _ = ai_service.submit_optimization(
        db_session,
        user_id,
        post.id,
        post_version=post.version,
        optimization_type="language",
        scope="body",
        provider_key="radio",
        instruction="语句更通顺",
    )
    db_session.commit()
    monkeypatch.setattr("app.services.radio.get_radio_client", lambda: FakeRadio())

    assert blog_task.optimize_run(run.id, "body", [], "语句更通顺") == "complete"

    db_session.expire_all()
    assert db_session.get(Post, post.id).markdown == "原始正文。"
    candidate = db_session.scalar(
        select(PostAICandidate).where(PostAICandidate.ai_run_id == run.id)
    )
    revision = db_session.get(PostRevision, candidate.candidate_revision_id)
    assert revision.markdown == "优化后的正文。"
    assert run.provider_key == "radio"


@requires_db
def test_malformed_output_fails_without_candidate(db_session, user_id, monkeypatch):
    from app.models.blog import PostAICandidate, PostAIRun
    from app.modules.posts import ai_service, service
    from app.services.llm.base import LLMError
    from app.workers.tasks import blog as blog_task

    _make_skill(db_session, user_id)
    post = service.create_post(db_session, user_id, title="t", markdown="body")
    db_session.commit()
    _job, run, _ = ai_service.submit_optimization(
        db_session, user_id, post.id, post_version=post.version,
        optimization_type="full", provider_key="aiassist",
    )
    db_session.commit()

    _inject_gateway(monkeypatch, _FakeGateway(error=LLMError("invalid_structured_output", "bad")))
    assert blog_task.optimize_run(run.id, "all", [], None) == "failed"

    db_session.expire_all()
    assert db_session.get(PostAIRun, run.id).outcome == "failed"
    assert db_session.scalar(
        __import__("sqlalchemy").select(PostAICandidate).where(PostAICandidate.ai_run_id == run.id)
    ) is None


@requires_db
def test_protected_code_change_makes_partial_candidate(db_session, user_id, monkeypatch):
    from app.models.blog import PostAICandidate
    from app.modules.posts import ai_service, service
    from app.workers.tasks import blog as blog_task

    _make_skill(db_session, user_id)
    post = service.create_post(
        db_session, user_id, title="t", markdown="讲解\n\n```\nprint(1)\n```",
    )
    db_session.commit()
    _job, run, _ = ai_service.submit_optimization(
        db_session, user_id, post.id, post_version=post.version,
        optimization_type="full", provider_key="aiassist",
    )
    db_session.commit()

    # AI changed the code inside the block — a blocking protected-token change.
    _inject_gateway(monkeypatch, _FakeGateway(result=_opt(markdown="讲解\n\n```\nprint(2)\n```")))
    outcome = blog_task.optimize_run(run.id, "all", [], None)
    assert outcome == "partial"

    db_session.expire_all()
    cand = db_session.scalar(
        __import__("sqlalchemy").select(PostAICandidate).where(PostAICandidate.ai_run_id == run.id)
    )
    assert cand.status == "merge_required"
    assert cand.validation_json["rejected_fields"] == ["markdown"]


@requires_db
def test_no_skill_configured_is_rejected(db_session, user_id):
    from app.core.errors import NotFoundError
    from app.modules.posts import ai_service, service

    post = service.create_post(db_session, user_id, title="t", markdown="body")
    db_session.commit()
    with pytest.raises(NotFoundError):
        ai_service.submit_optimization(
            db_session, user_id, post.id, post_version=post.version, optimization_type="full",
        )
