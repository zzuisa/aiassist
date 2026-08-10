"""Skill scope resolution (spec 005, US5, T098).

Resolution order is manual → content_type → content_class → global, with each
step skipped when the skill is disabled/deleted or its current version is
incomplete. These use a real session (resolution is a DB query) but assert pure
matching behaviour.
"""

from __future__ import annotations

import pytest

from tests.conftest import requires_db

pytestmark = [pytest.mark.unit, pytest.mark.integration]


def _config():
    return {
        "schema_version": "blog-skill-config.v1",
        "applicable_content_classes": ["essay"],
        "applicable_content_type_ids": [],
        "processing_goal": "g",
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


def _skill(session, user_id, name, *, config=True, enabled=True):
    from app.modules.posts import skill_service

    s = skill_service.create_skill(
        session,
        user_id,
        name=name,
        config=_config() if config else None,
    )
    if not enabled:
        s.enabled = False
    session.flush()
    return s


@requires_db
def test_manual_wins_over_defaults(db_session, make_user):
    from app.modules.posts import skill_service

    uid = make_user().id
    manual = _skill(db_session, uid, "manual")
    glob = _skill(db_session, uid, "global")
    skill_service.set_skill_default(db_session, uid, "global", "*", glob.id)
    db_session.commit()

    skill, _v = skill_service.resolve_skill(db_session, uid, manual_skill_id=manual.id)
    assert skill.id == manual.id


@requires_db
def test_content_class_beats_global(db_session, make_user):
    from app.modules.posts import skill_service

    uid = make_user().id
    cls = _skill(db_session, uid, "class")
    glob = _skill(db_session, uid, "global")
    skill_service.set_skill_default(db_session, uid, "content_class", "technical", cls.id)
    skill_service.set_skill_default(db_session, uid, "global", "*", glob.id)
    db_session.commit()

    skill, _v = skill_service.resolve_skill(db_session, uid, content_class="technical")
    assert skill.id == cls.id


@requires_db
def test_disabled_default_falls_through_to_global(db_session, make_user):
    from app.modules.posts import skill_service

    uid = make_user().id
    cls = _skill(db_session, uid, "class", enabled=False)
    glob = _skill(db_session, uid, "global")
    skill_service.set_skill_default(db_session, uid, "content_class", "technical", cls.id)
    skill_service.set_skill_default(db_session, uid, "global", "*", glob.id)
    db_session.commit()

    skill, _v = skill_service.resolve_skill(db_session, uid, content_class="technical")
    assert skill.id == glob.id  # disabled class default is skipped


@requires_db
def test_incomplete_version_is_not_resolved(db_session, make_user):
    from app.core.errors import NotFoundError
    from app.modules.posts import skill_service

    uid = make_user().id
    # A skill with no version (incomplete) set as global default.
    empty = _skill(db_session, uid, "empty", config=False)
    skill_service.set_skill_default(db_session, uid, "global", "*", empty.id)
    db_session.commit()

    with pytest.raises(NotFoundError):
        skill_service.resolve_skill(db_session, uid, content_class="essay")


@requires_db
def test_no_skill_raises(db_session, make_user):
    from app.core.errors import NotFoundError
    from app.modules.posts import skill_service

    uid = make_user().id
    db_session.commit()
    with pytest.raises(NotFoundError):
        skill_service.resolve_skill(db_session, uid, content_class="essay")
