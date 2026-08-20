from __future__ import annotations


def test_safe_capability_name_is_anthropic_compatible_and_stable() -> None:
    from app.modules.agent.capability_snapshot_service import safe_capability_name

    first = safe_capability_name("blog", "blog.search_posts")
    second = safe_capability_name("blog", "blog.search_posts")

    assert first == second
    assert first == "blog-blog-search_posts"
    assert len(first) <= 64
    assert all(character.isalnum() or character in "_-" for character in first)


def test_long_provider_names_keep_a_stable_collision_resistant_suffix() -> None:
    from app.modules.agent.capability_snapshot_service import safe_capability_name

    left = safe_capability_name("internal-blog", "x" * 100 + "a")
    right = safe_capability_name("internal-blog", "x" * 100 + "b")

    assert len(left) <= 64
    assert len(right) <= 64
    assert left != right
