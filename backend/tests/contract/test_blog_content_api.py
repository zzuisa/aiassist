"""Blog capture API contract: clipboard / URL / quick / blank (US1, T028).

Asserts the request/response shape of the durable capture endpoints against the
OpenAPI CaptureResult contract, including the pending-Job semantics for URL.
"""

from __future__ import annotations

import pytest
from app.modules.auth import service as auth_service

pytestmark = [pytest.mark.contract, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _reset():
    auth_service.reset_login_throttle()
    yield


def _login(client, email):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _assert_capture_shape(body, *, expect_job):
    assert set(body) == {"post", "source", "job", "warnings"}
    assert isinstance(body["warnings"], list)
    post, source = body["post"], body["source"]
    assert post["id"] and post["content_status"]
    assert source["id"] and source["source_type"] and source["status"]
    assert source["captured_at"]
    if expect_job:
        assert body["job"] is not None
        assert body["job"]["id"] and body["job"]["status"]
    else:
        assert body["job"] is None


def test_blank_capture_creates_draft(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post("/api/v1/posts/captures/blank", json={"title": "空白"}, headers=h)
    assert r.status_code == 201
    body = r.json()
    _assert_capture_shape(body, expect_job=False)
    assert body["post"]["content_status"] == "draft"
    assert body["source"]["source_type"] == "blank"


def test_clipboard_capture_normalizes_html(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post(
        "/api/v1/posts/captures/clipboard",
        json={"raw_content": "<h1>标题</h1><p>正文 <b>粗</b></p>", "detected_format": "html"},
        headers=h,
    )
    assert r.status_code == 201
    body = r.json()
    _assert_capture_shape(body, expect_job=False)
    assert body["source"]["status"] == "completed"
    assert "# 标题" in body["post"]["markdown"]
    assert body["source"]["original_text"]  # raw preserved


def test_clipboard_rejects_bad_format(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post(
        "/api/v1/posts/captures/clipboard",
        json={"raw_content": "x", "detected_format": "not-real"},
        headers=h,
    )
    assert r.status_code == 422


def test_url_capture_is_durable_and_async(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post(
        "/api/v1/posts/captures/url",
        json={"url": "https://example.com/article", "note": "读一读"},
        headers=h,
    )
    assert r.status_code == 202
    body = r.json()
    _assert_capture_shape(body, expect_job=True)
    assert body["post"]["content_status"] == "pending_parse"
    assert body["source"]["source_type"] == "url"
    assert body["source"]["status"] == "pending"
    assert body["source"]["original_url"] == "https://example.com/article"
    assert body["job"]["job_type"] == "blog.parse"


def test_url_capture_rejects_unsafe_scheme(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post(
        "/api/v1/posts/captures/url",
        json={"url": "file:///etc/passwd"},
        headers=h,
    )
    assert r.status_code == 422


def test_quick_capture_goes_to_triage(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.post(
        "/api/v1/posts/captures/quick",
        json={"content": "记一笔"},
        headers=h,
    )
    assert r.status_code == 201
    body = r.json()
    _assert_capture_shape(body, expect_job=False)
    assert body["post"]["content_status"] == "triage"
    assert body["post"]["markdown"] == "记一笔"


def test_category_collection_can_be_created_listed_and_assigned(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    created = client.post(
        "/api/v1/blog/taxonomy/category",
        json={"name": "AI Assist 修复复盘", "description": "持续记录系统修复"},
        headers=h,
    )
    assert created.status_code == 201
    category = created.json()
    assert category["kind"] == "category"
    assert category["usage_count"] == 0

    post = client.post(
        "/api/v1/posts",
        json={"title": "修复报告", "markdown": "# 报告"},
        headers=h,
    ).json()
    assigned = client.patch(
        f"/api/v1/posts/{post['id']}",
        json={"version": post["version"], "category_id": category["id"]},
        headers=h,
    )
    assert assigned.status_code == 200
    assert assigned.json()["category_id"] == category["id"]

    listed = client.get("/api/v1/blog/taxonomy/category").json()
    assert listed[0]["name"] == "AI Assist 修复复盘"
    assert listed[0]["usage_count"] == 1


def test_article_list_exposes_and_filters_primary_category(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    category = client.post(
        "/api/v1/blog/taxonomy/category",
        json={"name": "移动端设计"},
        headers=h,
    ).json()
    post = client.post(
        "/api/v1/posts",
        json={"title": "手机文章", "markdown": "正文"},
        headers=h,
    ).json()
    assigned = client.patch(
        f"/api/v1/posts/{post['id']}",
        json={"version": post["version"], "category_id": category["id"]},
        headers=h,
    )
    assert assigned.status_code == 200

    result = client.get(f"/api/v1/blog/articles?category_id={category['id']}", headers=h)
    assert result.status_code == 200
    assert result.json()["items"][0]["category_id"] == category["id"]


def test_blog_search_and_timeline_return_deep_fields_and_time_basis(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = client.post(
        "/api/v1/posts",
        json={"title": "数据库复盘", "markdown": "正文包含 CrashLoopBackOff"},
        headers=h,
    ).json()
    patched = client.patch(
        f"/api/v1/posts/{post['id']}",
        json={
            "version": post["version"],
            "summary": "搜索摘要 marker-42",
            "occurred_at": "2025-04-12T10:00:00Z",
            "structured_data": {"incident_id": "INC-42"},
        },
        headers=h,
    )
    assert patched.status_code == 200

    searched = client.get(
        "/api/v1/blog/search",
        params={"q": "marker-42"},
        headers=h,
    )
    assert searched.status_code == 200
    assert searched.json()["items"][0]["id"] == post["id"]
    assert "summary" in searched.json()["items"][0]["matched_fields"]

    timeline = client.get(
        "/api/v1/blog/timeline",
        params={"year": 2025},
        headers=h,
    )
    assert timeline.status_code == 200
    item = timeline.json()["items"][0]
    assert item["id"] == post["id"]
    assert item["time_basis"] == "occurred_at"


def test_source_detail_readable_by_owner(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    cap = client.post("/api/v1/posts/captures/quick", json={"content": "细节"}, headers=h).json()
    sid = cap["source"]["id"]
    # Read-only source endpoints use the authenticated cookie without requiring
    # the write-only CSRF header, matching the browser API client.
    r = client.get(f"/api/v1/post-sources/{sid}")
    assert r.status_code == 200
    assert r.json()["id"] == sid


# ---------------------------------------------------------------------------
# US2: Post patch, content types, source summary (T046)
# ---------------------------------------------------------------------------


def _blank_post(client, h):
    return client.post("/api/v1/posts/captures/blank", json={"title": "草稿"}, headers=h).json()[
        "post"
    ]


def test_new_post_defaults_to_rich_editor(client, make_user):
    user = make_user()
    post = _blank_post(client, _login(client, user.email))
    assert post["editor_mode"] == "rich"


def test_patch_updates_common_fields_and_bumps_version(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = _blank_post(client, h)
    r = client.patch(
        f"/api/v1/posts/{post['id']}",
        json={
            "version": post["version"],
            "title": "正式标题",
            "subtitle": "副标题",
            "markdown": "# 正文",
            "content_class": "technical",
            "editor_mode": "rich",
        },
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "正式标题"
    assert body["subtitle"] == "副标题"
    assert body["content_class"] == "technical"
    assert body["editor_mode"] == "rich"
    assert body["version"] == post["version"] + 1


def test_patch_requires_matching_version(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = _blank_post(client, h)
    r = client.patch(
        f"/api/v1/posts/{post['id']}",
        json={"version": post["version"] + 99, "title": "x"},
        headers=h,
    )
    assert r.status_code == 409


def test_patch_rejects_unknown_content_class(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = _blank_post(client, h)
    r = client.patch(
        f"/api/v1/posts/{post['id']}",
        json={"version": post["version"], "content_class": "not-a-class"},
        headers=h,
    )
    assert r.status_code == 422


def test_get_post_includes_source_summary(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    # A quick capture creates a post with one source.
    cap = client.post("/api/v1/posts/captures/quick", json={"content": "来源"}, headers=h).json()
    r = client.get(f"/api/v1/posts/{cap['post']['id']}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body["source_summary"]) == 1
    assert body["source_summary"][0]["source_type"] == "quick"
    assert body["ai_summary"]["optimization_count"] == 0


def test_content_type_create_list_and_update(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    created = client.post(
        "/api/v1/blog/content-types",
        json={
            "content_class": "technical",
            "key": "my-tutorial",
            "name": "我的教程",
            "field_schema": {"type": "object", "properties": {"lang": {"type": "string"}}},
            "enabled": True,
        },
        headers=h,
    )
    assert created.status_code == 201
    ct = created.json()
    assert ct["key"] == "my-tutorial"
    assert ct["schema_version"] == 1

    listed = client.get("/api/v1/blog/content-types", headers=h).json()
    assert any(c["id"] == ct["id"] for c in listed)

    # Changing the field_schema bumps schema_version.
    updated = client.patch(
        f"/api/v1/blog/content-types/{ct['id']}",
        json={
            "content_class": "technical",
            "key": "my-tutorial",
            "name": "我的教程 v2",
            "field_schema": {
                "type": "object",
                "properties": {"lang": {"type": "string"}, "level": {"type": "string"}},
            },
            "enabled": True,
        },
        headers=h,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "我的教程 v2"
    assert updated.json()["schema_version"] == 2


def test_content_type_rejects_duplicate_key(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    body = {
        "content_class": "essay",
        "key": "dup-key",
        "name": "N",
        "field_schema": {},
        "enabled": True,
    }
    assert client.post("/api/v1/blog/content-types", json=body, headers=h).status_code == 201
    assert client.post("/api/v1/blog/content-types", json=body, headers=h).status_code == 422


# ---------------------------------------------------------------------------
# US3: optimize endpoint contract (T062)
# ---------------------------------------------------------------------------


def _seed_global_skill(user_id):
    """Create a complete Skill + global default directly so optimize can resolve."""
    import uuid as _uuid

    from app.db.session import session_scope
    from app.models.blog import BlogSkill, BlogSkillDefault, BlogSkillVersion

    config = {
        "schema_version": "blog-skill-config.v1",
        "applicable_content_classes": ["essay"],
        "applicable_content_type_ids": [],
        "processing_goal": "improve",
        "content_rules": [],
        "title_rules": [],
        "summary_rules": [],
        "body_structure": [],
        "taxonomy_rules": [],
        "keyword_rules": [],
        "prohibitions": ["no invention"],
        "field_policies": {"title": "allow_overwrite"},
        "output_fields": ["title"],
        "output_schema": "blog-optimization.v1",
        "validation_rules": [],
        "recommended_model": "m",
        "max_content_chars": 200000,
        "long_content_strategy": "reject",
    }
    with session_scope() as s:
        skill = BlogSkill(id=_uuid.uuid4(), user_id=user_id, name="s", enabled=True)
        s.add(skill)
        s.flush()
        v = BlogSkillVersion(
            id=_uuid.uuid4(),
            user_id=user_id,
            skill_id=skill.id,
            version_number=1,
            config_json=config,
            schema_version="blog-skill-config.v1",
            recommended_model="m",
            max_content_chars=200000,
            long_content_strategy="reject",
        )
        s.add(v)
        s.flush()
        skill.current_version_id = v.id
        s.add(
            BlogSkillDefault(
                id=_uuid.uuid4(),
                user_id=user_id,
                scope_type="global",
                scope_key="*",
                skill_id=skill.id,
            )
        )


def test_optimize_returns_blog_job_202(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    _seed_global_skill(user.id)
    post = _blank_post(client, h)
    r = client.post(
        f"/api/v1/posts/{post['id']}/optimize",
        json={"post_version": post["version"], "optimization_type": "full"},
        headers=h,
    )
    assert r.status_code == 202
    body = r.json()
    assert body["job_type"] == "blog.optimize"
    assert body["display_status"] in ("ai_queued", "ai_processing", "ai_review")
    assert body["status"] in ("pending", "queued", "processing", "waiting_user")


def test_optimize_rejects_stale_version(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    _seed_global_skill(user.id)
    post = _blank_post(client, h)
    r = client.post(
        f"/api/v1/posts/{post['id']}/optimize",
        json={"post_version": post["version"] + 5, "optimization_type": "full"},
        headers=h,
    )
    assert r.status_code == 409


def test_optimize_without_skill_is_404(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post = _blank_post(client, h)
    r = client.post(
        f"/api/v1/posts/{post['id']}/optimize",
        json={"post_version": post["version"], "optimization_type": "full"},
        headers=h,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Candidate review + decision + version compare (spec 005, US4, T080)
# ---------------------------------------------------------------------------


def _seed_candidate(user_id, *, base_md="V1正文", cand_md="AI正文"):
    """Seed a post + AI run + saved candidate directly; returns (post_id, cand_id)."""
    from app.db.session import session_scope
    from app.modules.posts import ai_service, service

    _seed_global_skill(user_id)
    with session_scope() as s:
        post = service.create_post(s, user_id, title="V1标题", markdown=base_md)
        post.summary = "V1摘要"
        s.flush()
        _job, run, _dup = ai_service.submit_optimization(
            s,
            user_id,
            post.id,
            post_version=post.version,
            optimization_type="full",
        )
        field_diff = {
            "title": {"from": "V1标题", "to": "AI标题", "classification": "allow_overwrite"},
            "summary": {"from": "V1摘要", "to": "AI摘要", "classification": "allow_overwrite"},
            "markdown": {"from": base_md, "to": cand_md, "classification": "allow_overwrite"},
        }
        candidate = ai_service.save_candidate(
            s,
            run,
            candidate_markdown=cand_md,
            field_diff=field_diff,
            validation={"outcome": "complete"},
            outcome="complete",
        )
        return str(post.id), str(candidate.id)


def test_candidate_list_and_detail_shape(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post_id, cand_id = _seed_candidate(user.id)

    lst = client.get(f"/api/v1/posts/{post_id}/candidates", headers=h)
    assert lst.status_code == 200
    assert any(c["id"] == cand_id and c["status"] == "pending" for c in lst.json())

    detail = client.get(f"/api/v1/blog/ai/candidates/{cand_id}", headers=h)
    assert detail.status_code == 200
    body = detail.json()
    assert set(body) >= {"candidate", "post_version", "field_diff", "body_diff", "conflicts"}
    assert body["field_diff"]["summary"]["candidate"] == "AI摘要"
    assert body["body_diff"]["changed"] is True


def test_candidate_decision_applies_selected_field(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post_id, cand_id = _seed_candidate(user.id)
    detail = client.get(f"/api/v1/blog/ai/candidates/{cand_id}", headers=h).json()

    r = client.post(
        f"/api/v1/blog/ai/candidates/{cand_id}/decide",
        json={
            "post_version": detail["post_version"],
            "action": "apply_fields",
            "selected_fields": ["summary"],
        },
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["candidate"]["status"] == "applied"
    # Body stays as V1 (only summary applied).
    got = client.get(f"/api/v1/posts/{post_id}", headers=h).json()
    assert got["summary"] == "AI摘要"
    assert got["markdown"] == "V1正文"


def test_candidate_decision_rejects_bad_action(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    _post_id, cand_id = _seed_candidate(user.id)
    detail = client.get(f"/api/v1/blog/ai/candidates/{cand_id}", headers=h).json()
    r = client.post(
        f"/api/v1/blog/ai/candidates/{cand_id}/decide",
        json={"post_version": detail["post_version"], "action": "explode"},
        headers=h,
    )
    assert r.status_code == 422  # pattern-constrained action


def test_version_list_and_compare_shape(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    post_id, cand_id = _seed_candidate(user.id)
    # Apply to create a second applied revision so the timeline has ≥2 entries.
    detail = client.get(f"/api/v1/blog/ai/candidates/{cand_id}", headers=h).json()
    client.post(
        f"/api/v1/blog/ai/candidates/{cand_id}/decide",
        json={"post_version": detail["post_version"], "action": "apply_all"},
        headers=h,
    )
    revs = client.get(f"/api/v1/posts/{post_id}/revisions", headers=h)
    assert revs.status_code == 200
    items = revs.json()
    assert len(items) >= 2
    a, b = items[-1]["id"], items[0]["id"]
    cmp = client.get(
        f"/api/v1/posts/{post_id}/revisions/compare",
        params={"from_revision": a, "to_revision": b},
        headers=h,
    )
    assert cmp.status_code == 200
    assert set(cmp.json()) >= {"from_revision_id", "to_revision_id", "body_diff", "field_diff"}


# ---------------------------------------------------------------------------
# Skill management (spec 005, US5, T097)
# ---------------------------------------------------------------------------


def _skill_config(goal="v1"):
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


def test_skill_list_lazily_seeds_a_default(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    r = client.get("/api/v1/blog/skills", headers=h)
    assert r.status_code == 200
    skills = r.json()
    assert len(skills) >= 1
    seed = skills[0]
    assert seed["current_version"] is not None
    assert seed["current_version_complete"] is True


def test_skill_crud_version_and_restore(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    # Create with a v1 config.
    created = client.post(
        "/api/v1/blog/skills",
        json={"name": "我的技能", "config": _skill_config("v1")},
        headers=h,
    )
    assert created.status_code == 201
    skill = created.json()
    sid = skill["id"]
    assert skill["current_version"]["version_number"] == 1

    # Edit-as-new-version.
    v2 = client.post(
        f"/api/v1/blog/skills/{sid}/versions",
        json={"config": _skill_config("v2")},
        headers=h,
    )
    assert v2.status_code == 201
    assert v2.json()["version_number"] == 2

    versions = client.get(f"/api/v1/blog/skills/{sid}/versions", headers=h).json()
    assert [v["version_number"] for v in versions] == [2, 1]
    v1_id = versions[1]["id"]

    # Restore v1 → appends v3.
    restored = client.post(f"/api/v1/blog/skills/{sid}/versions/{v1_id}/restore", headers=h)
    assert restored.status_code == 201
    assert restored.json()["version_number"] == 3
    assert restored.json()["config"]["processing_goal"] == "v1"


def test_skill_invalid_config_is_422(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    bad = dict(_skill_config())
    del bad["prohibitions"]  # required, min_length 1
    r = client.post("/api/v1/blog/skills", json={"name": "坏技能", "config": bad}, headers=h)
    assert r.status_code in (400, 422)


def test_skill_default_set_and_list(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    sid = client.post(
        "/api/v1/blog/skills", json={"name": "默认", "config": _skill_config()}, headers=h
    ).json()["id"]
    put = client.put(
        "/api/v1/blog/skills/defaults",
        json={"scope_type": "content_class", "scope_key": "technical", "skill_id": sid},
        headers=h,
    )
    assert put.status_code == 200
    lst = client.get("/api/v1/blog/skills/defaults/list", headers=h).json()
    assert any(
        d["scope_type"] == "content_class"
        and d["scope_key"] == "technical"
        and d["skill_id"] == sid
        for d in lst
    )


def test_skill_enable_disable(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    sid = client.post(
        "/api/v1/blog/skills", json={"name": "开关", "config": _skill_config()}, headers=h
    ).json()["id"]
    off = client.post(f"/api/v1/blog/skills/{sid}/enabled", json={"enabled": False}, headers=h)
    assert off.status_code == 200
    assert off.json()["enabled"] is False


# ---------------------------------------------------------------------------
# Article management: list / triage / batch / merge (spec 005, US6, T112)
# ---------------------------------------------------------------------------


def test_article_list_shape_and_filters(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    _blank_post(client, h)
    r = client.get("/api/v1/blog/articles", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "next_cursor", "total", "counts_by_status"}
    assert body["total"] >= 1
    assert isinstance(body["counts_by_status"], dict)
    row = body["items"][0]
    assert set(row) >= {"id", "title", "content_status", "ai_state", "source_count"}


def test_triage_shape(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    _blank_post(client, h)
    r = client.get("/api/v1/blog/triage", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "counts_by_reason"}
    assert set(body["counts_by_reason"]) == {"quick", "failed", "stale", "draft"}


def test_batch_reports_per_item_partial_failure(client, make_user):
    import uuid as _uuid

    user = make_user()
    h = _login(client, user.email)
    good = _blank_post(client, h)["id"]
    bogus = str(_uuid.uuid4())  # not owned → this item fails, the good one succeeds
    r = client.post(
        "/api/v1/blog/articles/batch",
        json={"post_ids": [good, bogus], "op": "set_class", "params": {"content_class": "life"}},
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    by_id = {x["id"]: x for x in body["results"]}
    assert by_id[good]["ok"] is True
    assert by_id[bogus]["ok"] is False and "error" in by_id[bogus]


def test_merge_endpoint_orders_and_discards_secondary(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    primary = _blank_post(client, h)
    secondary = _blank_post(client, h)
    # Give each a distinct body.
    client.patch(
        f"/api/v1/posts/{primary['id']}",
        json={"version": primary["version"], "markdown": "正文甲"},
        headers=h,
    )
    client.patch(
        f"/api/v1/posts/{secondary['id']}",
        json={"version": secondary["version"], "markdown": "正文乙"},
        headers=h,
    )
    got = client.get(f"/api/v1/posts/{primary['id']}", headers=h).json()

    r = client.post(
        "/api/v1/blog/articles/merge",
        json={
            "primary_id": primary["id"],
            "secondary_id": secondary["id"],
            "primary_version": got["version"],
            "order": "primary_first",
        },
        headers=h,
    )
    assert r.status_code == 200
    merged = r.json()
    assert merged["markdown"].index("正文甲") < merged["markdown"].index("正文乙")
    # Secondary is discarded (excluded from the default list).
    listed = client.get("/api/v1/blog/articles", headers=h).json()
    assert secondary["id"] not in {i["id"] for i in listed["items"]}


def test_article_export_returns_markdown(client, make_user):
    user = make_user()
    h = _login(client, user.email)
    p = _blank_post(client, h)
    client.patch(
        f"/api/v1/posts/{p['id']}",
        json={"version": p["version"], "markdown": "# 导出内容"},
        headers=h,
    )
    r = client.get(f"/api/v1/blog/articles/{p['id']}/export", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["markdown"] == "# 导出内容"
    assert body["filename"].endswith(".md")
