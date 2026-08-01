"""Skill versioning + defaults + historical reproducibility (spec 005, US5, T099/T111).

Guarantees:
* editing a skill appends an immutable version and advances current_version_id;
* a run bound to an old version keeps resolving that exact version even after
  the skill is edited, disabled or soft-deleted (reproducibility, T111);
* a scope default is unique — setting it again replaces the target;
* restore appends a NEW version rather than mutating history.
"""

from __future__ import annotations

import pytest

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration]


def _config(goal="v1"):
    return {
        "schema_version": "blog-skill-config.v1",
        "applicable_content_classes": ["essay"],
        "applicable_content_type_ids": [],
        "processing_goal": goal,
        "content_rules": [],
        "title_rules": [],
        "summary_rules": [],
        "body_structure": [],
        "taxonomy_rules": [],
        "keyword_rules": [],
        "prohibitions": ["p"],
        "field_policies": {"title": "allow_overwrite"},
        "output_fields": ["title"],
        "output_schema": "blog-optimization.v1",
        "validation_rules": [],
        "recommended_model": "m",
        "max_content_chars": 200000,
        "long_content_strategy": "reject",
    }


@requires_db
def test_edit_appends_immutable_version(db_session, make_user):
    from app.modules.posts import skill_service

    uid = make_user().id
    skill = skill_service.create_skill(db_session, uid, name="s", config=_config("v1"))
    v1_id = skill.current_version_id
    v2 = skill_service.save_skill_version(db_session, uid, skill, config=_config("v2"))
    db_session.commit()

    assert skill.current_version_id == v2.id
    assert v2.version_number == 2
    # v1 is untouched and still fetchable.
    v1 = skill_service.get_skill_version(db_session, uid, v1_id)
    assert v1.config_json["processing_goal"] == "v1"


@requires_db
def test_run_keeps_old_version_after_edit_and_disable(db_session, make_user):
    """T111: a historical run resolves its bound version even after edit/disable."""
    from app.models.blog import PostAIRun
    from app.modules.posts import ai_service, service, skill_service

    uid = make_user().id
    skill = skill_service.create_skill(db_session, uid, name="s", config=_config("v1"))
    skill_service.set_skill_default(db_session, uid, "global", "*", skill.id)
    v1_id = skill.current_version_id
    post = service.create_post(db_session, uid, title="t", markdown="body")
    db_session.commit()

    _job, run, _dup = ai_service.submit_optimization(
        db_session,
        uid,
        post.id,
        post_version=post.version,
        optimization_type="full",
    )
    db_session.commit()
    assert run.skill_version_id == v1_id

    # Edit (new version) and then disable + soft-delete the skill.
    skill_service.save_skill_version(db_session, uid, skill, config=_config("v2"))
    skill_service.soft_delete_skill(db_session, uid, skill.id)
    db_session.commit()

    # The run still points at v1 and that version data still resolves.
    reloaded = db_session.get(PostAIRun, run.id)
    assert reloaded.skill_version_id == v1_id
    v1 = skill_service.get_skill_version(db_session, uid, v1_id)
    assert v1.config_json["processing_goal"] == "v1"


@requires_db
def test_default_is_unique_per_scope(db_session, make_user):
    from app.models.blog import BlogSkillDefault
    from app.modules.posts import skill_service
    from sqlalchemy import func, select

    uid = make_user().id
    a = skill_service.create_skill(db_session, uid, name="a", config=_config())
    b = skill_service.create_skill(db_session, uid, name="b", config=_config())
    skill_service.set_skill_default(db_session, uid, "global", "*", a.id)
    skill_service.set_skill_default(db_session, uid, "global", "*", b.id)
    db_session.commit()

    count = db_session.scalar(
        select(func.count())
        .select_from(BlogSkillDefault)
        .where(
            BlogSkillDefault.user_id == uid,
            BlogSkillDefault.scope_type == "global",
        )
    )
    assert count == 1
    row = db_session.scalar(select(BlogSkillDefault).where(BlogSkillDefault.user_id == uid))
    assert row.skill_id == b.id  # replaced, not duplicated


@requires_db
def test_restore_appends_new_version(db_session, make_user):
    from app.modules.posts import skill_service

    uid = make_user().id
    skill = skill_service.create_skill(db_session, uid, name="s", config=_config("v1"))
    v1_id = skill.current_version_id
    skill_service.save_skill_version(db_session, uid, skill, config=_config("v2"))
    db_session.commit()

    v3 = skill_service.restore_version(db_session, uid, skill.id, v1_id)
    db_session.commit()

    assert v3.version_number == 3
    assert v3.config_json["processing_goal"] == "v1"  # content of v1
    assert skill.current_version_id == v3.id  # current advanced, history intact


@requires_db
def test_seed_default_skills_is_idempotent(db_session, make_user):
    from app.modules.posts import skill_service

    uid = make_user().id
    first = skill_service.seed_default_skills(db_session, uid)
    db_session.commit()
    assert first is not None
    second = skill_service.seed_default_skills(db_session, uid)
    db_session.commit()
    assert second is None  # never re-seeds when the user already has a skill
    assert len(skill_service.list_skills(db_session, uid)) == 1
