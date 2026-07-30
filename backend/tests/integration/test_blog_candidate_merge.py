"""Candidate merge + decision (spec 005, US4, T081/T096).

Exercises the safe field-level apply loop directly against ai_service: a
candidate proposes several fields, the user edits the body after generation, and
applying only selected fields must leave the untouched body intact while
recording an immutable decision + new revision. Also covers apply-all, reject,
copy, version conflict and idempotent (already-decided) guarantees.
"""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration]


def _valid_skill_config() -> dict:
    return {
        "schema_version": "blog-skill-config.v1",
        "applicable_content_classes": ["technical", "essay"],
        "applicable_content_type_ids": [],
        "processing_goal": "improve clarity",
        "content_rules": [], "title_rules": [], "summary_rules": [],
        "body_structure": [], "taxonomy_rules": [], "keyword_rules": [],
        "prohibitions": ["do not invent facts"],
        "field_policies": {"title": "allow_overwrite", "summary": "allow_overwrite"},
        "output_fields": ["title", "summary", "markdown"],
        "output_schema": "blog-optimization.v1",
        "validation_rules": [], "recommended_model": "test-model",
        "max_content_chars": 200000, "long_content_strategy": "reject",
    }


def _make_skill(session, user_id):
    from app.models.blog import BlogSkill, BlogSkillDefault, BlogSkillVersion

    skill = BlogSkill(id=uuid.uuid4(), user_id=user_id, name="默认技能", enabled=True)
    session.add(skill)
    session.flush()
    version = BlogSkillVersion(
        id=uuid.uuid4(), user_id=user_id, skill_id=skill.id, version_number=1,
        config_json=_valid_skill_config(), schema_version="blog-skill-config.v1",
        recommended_model="test-model", max_content_chars=200000, long_content_strategy="reject",
    )
    session.add(version)
    session.flush()
    skill.current_version_id = version.id
    session.add(BlogSkillDefault(
        id=uuid.uuid4(), user_id=user_id, scope_type="global", scope_key="*", skill_id=skill.id,
    ))
    session.flush()
    return skill


def _make_candidate(session, user_id, *, base_title="V1标题", base_summary="V1摘要",
                    base_md="V1正文", cand_title="AI标题", cand_summary="AI摘要",
                    cand_md="AI正文", outcome="complete"):
    """Create a post + AI run + saved candidate proposing title/summary/markdown."""
    from app.modules.posts import ai_service, service

    _make_skill(session, user_id)
    post = service.create_post(session, user_id, title=base_title, markdown=base_md)
    post.summary = base_summary
    session.flush()
    _job, run, _dup = ai_service.submit_optimization(
        session, user_id, post.id, post_version=post.version, optimization_type="full",
    )
    field_diff = {
        "title": {"from": base_title, "to": cand_title, "classification": "allow_overwrite"},
        "summary": {"from": base_summary, "to": cand_summary, "classification": "allow_overwrite"},
        "markdown": {"from": base_md, "to": cand_md, "classification": "allow_overwrite"},
    }
    candidate = ai_service.save_candidate(
        session, run, candidate_markdown=cand_md, field_diff=field_diff,
        validation={"outcome": outcome}, outcome=outcome,
    )
    session.commit()
    return post, candidate


@requires_db
def test_apply_selected_field_preserves_user_body(db_session, make_user):
    """Generate from V1, edit body to V2, apply only summary → body stays V2."""
    from app.models.posts import Post
    from app.modules.posts import ai_service

    user_id = make_user().id
    post, candidate = _make_candidate(db_session, user_id)

    # User edits the body after the candidate was generated.
    post.markdown = "用户手改的正文V2"
    post.version += 1
    db_session.commit()
    version_before = post.version

    result = ai_service.decide_candidate(
        db_session, user_id, candidate.id,
        action="apply_fields", selected_fields=["summary"], current_version=version_before,
    )
    db_session.commit()

    p = db_session.get(Post, post.id)
    assert p.summary == "AI摘要"          # selected field applied
    assert p.markdown == "用户手改的正文V2"  # untouched body preserved
    assert p.title == "V1标题"             # unselected metadata preserved
    assert p.version == version_before + 1
    assert result["candidate"]["status"] == "applied"
    assert result["result_revision_id"]


@requires_db
def test_apply_all_uses_candidate_body(db_session, make_user):
    from app.models.posts import Post
    from app.modules.posts import ai_service

    user_id = make_user().id
    post, candidate = _make_candidate(db_session, user_id)

    ai_service.decide_candidate(
        db_session, user_id, candidate.id, action="apply_all", current_version=post.version,
    )
    db_session.commit()

    p = db_session.get(Post, post.id)
    assert p.markdown == "AI正文"
    assert p.title == "AI标题"
    assert p.summary == "AI摘要"


@requires_db
def test_reject_leaves_article_unchanged(db_session, make_user):
    from app.models.posts import Post
    from app.modules.posts import ai_service

    user_id = make_user().id
    post, candidate = _make_candidate(db_session, user_id)
    version_before = post.version

    ai_service.decide_candidate(
        db_session, user_id, candidate.id, action="reject", current_version=version_before,
    )
    db_session.commit()

    p = db_session.get(Post, post.id)
    assert p.markdown == "V1正文"
    assert p.summary == "V1摘要"
    assert p.version == version_before  # rejecting never bumps the article
    from app.models.blog import PostAICandidate
    assert db_session.get(PostAICandidate, candidate.id).status == "rejected"


@requires_db
def test_copy_forks_new_draft_without_touching_source(db_session, make_user):
    from app.models.blog import PostAICandidate
    from app.models.posts import Post
    from app.modules.posts import ai_service

    user_id = make_user().id
    post, candidate = _make_candidate(db_session, user_id)

    result = ai_service.decide_candidate(
        db_session, user_id, candidate.id, action="copy", current_version=post.version,
    )
    db_session.commit()

    src = db_session.get(Post, post.id)
    assert src.markdown == "V1正文"  # source untouched
    assert db_session.get(PostAICandidate, candidate.id).status == "copied"
    # A new draft post now exists carrying the AI content.
    forks = [
        p for p in db_session.query(Post).filter(Post.user_id == user_id).all()
        if p.id != post.id
    ]
    assert len(forks) == 1
    assert forks[0].markdown == "AI正文"
    assert result["result_revision_id"]


@requires_db
def test_version_conflict_blocks_apply(db_session, make_user):
    from app.core.errors import VersionConflictError
    from app.modules.posts import ai_service

    user_id = make_user().id
    post, candidate = _make_candidate(db_session, user_id)

    with pytest.raises(VersionConflictError):
        ai_service.decide_candidate(
            db_session, user_id, candidate.id,
            action="apply_all", current_version=post.version + 5,
        )


@requires_db
def test_terminal_decision_is_immutable_and_recorded(db_session, make_user):
    """T096: every terminal action records a decision and cannot be re-decided."""
    from app.core.errors import ConflictError
    from app.models.blog import PostCandidateDecision
    from app.modules.posts import ai_service

    user_id = make_user().id
    post, candidate = _make_candidate(db_session, user_id)

    ai_service.decide_candidate(
        db_session, user_id, candidate.id,
        action="apply_fields", selected_fields=["summary"], current_version=post.version,
    )
    db_session.commit()

    decisions = (
        db_session.query(PostCandidateDecision)
        .filter(PostCandidateDecision.candidate_id == candidate.id)
        .all()
    )
    assert len(decisions) == 1
    assert decisions[0].action == "apply_fields"
    assert decisions[0].selected_fields_json == {"fields": ["summary"]}
    assert decisions[0].result_revision_id is not None

    # A second decision on the same candidate is rejected.
    from app.models.posts import Post
    p = db_session.get(Post, post.id)
    with pytest.raises(ConflictError):
        ai_service.decide_candidate(
            db_session, user_id, candidate.id,
            action="reject", current_version=p.version,
        )
