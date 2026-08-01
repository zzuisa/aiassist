"""Model-level guarantees for spec 005 blog tables (T009).

Covers owner scoping, one-default-per-scope uniqueness, immutable version
numbering and DB-enforced status/enum constraints. Runs against the real
PostgreSQL test database so CHECK constraints and unique indexes are exercised.
"""

from __future__ import annotations

import uuid

import pytest
from app.db.session import session_scope
from app.models.blog import (
    BlogSkill,
    BlogSkillDefault,
    BlogSkillVersion,
    PostSource,
)
from app.models.posts import Post
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.integration]


def _skill(session, user_id: uuid.UUID, name: str = "默认技能") -> BlogSkill:
    skill = BlogSkill(id=uuid.uuid4(), user_id=user_id, name=name, enabled=True)
    session.add(skill)
    session.flush()
    return skill


def test_post_source_requires_owner(make_user):
    make_user()
    with pytest.raises(IntegrityError), session_scope() as s:
        s.add(
            PostSource(
                id=uuid.uuid4(),
                user_id=None,  # type: ignore[arg-type]
                source_type="clipboard",
                status="saved",
            )
        )


def test_url_source_requires_original_url(make_user):
    user = make_user()
    with pytest.raises(IntegrityError), session_scope() as s:
        s.add(
            PostSource(
                id=uuid.uuid4(),
                user_id=user.id,
                source_type="url",
                status="pending",
                original_url=None,
            )
        )


def test_one_default_per_scope(make_user):
    user = make_user()
    with pytest.raises(IntegrityError), session_scope() as s:
        skill = _skill(s, user.id)
        for _ in range(2):
            s.add(
                BlogSkillDefault(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    scope_type="global",
                    scope_key="*",
                    skill_id=skill.id,
                )
            )
        s.flush()


def test_skill_version_number_is_unique_per_skill(make_user):
    user = make_user()
    with pytest.raises(IntegrityError), session_scope() as s:
        skill = _skill(s, user.id)
        for _ in range(2):
            s.add(
                BlogSkillVersion(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    skill_id=skill.id,
                    version_number=1,
                    config_json={},
                )
            )
        s.flush()


def test_invalid_content_status_rejected(make_user):
    user = make_user()
    with pytest.raises(IntegrityError), session_scope() as s:
        s.add(
            Post(
                id=uuid.uuid4(),
                user_id=user.id,
                title="坏状态",
                markdown="x",
                status="draft",
                content_status="not_a_real_status",
            )
        )


def test_invalid_content_class_rejected(make_user):
    user = make_user()
    with pytest.raises(IntegrityError), session_scope() as s:
        s.add(
            Post(
                id=uuid.uuid4(),
                user_id=user.id,
                title="坏分类",
                markdown="x",
                status="draft",
                content_class="nonsense",
            )
        )
