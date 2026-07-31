"""Post endpoints: private CRUD/revisions/publish + public post/RSS."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.modules.posts import rendering, service, taxonomy_service
from app.modules.posts.schemas import (
    GenerateBody,
    PostCreate,
    PostOut,
    PostPatch,
    PublishBody,
    RestoreRevisionBody,
    RevisionOut,
    TaxonomyItemOut,
    TaxonomyWrite,
    post_detail_out,
    post_out,
    revision_out,
)
from app.services.storage.base import ObjectNotFoundError
from app.services.storage.providers.local import get_storage

private_router = APIRouter(prefix="/posts", tags=["posts"])
public_router = APIRouter(prefix="/public", tags=["public"])

# Additive blog routers (spec 005, T025). Endpoints are attached by later user
# stories; the routers are declared and registered here so the URL surface under
# /api/v1 is stable and existing /posts routes stay untouched.
capture_router = APIRouter(prefix="/blog/capture", tags=["blog-capture"])
taxonomy_router = APIRouter(prefix="/blog/taxonomy", tags=["blog-taxonomy"])
ai_router = APIRouter(prefix="/blog/ai", tags=["blog-ai"])
query_router = APIRouter(prefix="/blog/query", tags=["blog-query"])


@taxonomy_router.get("/{kind}")
def list_taxonomy(
    kind: str,
    enabled: bool | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TaxonomyItemOut]:
    return [
        TaxonomyItemOut(**item)
        for item in taxonomy_service.list_items(db, user.id, kind, enabled=enabled)
    ]


@taxonomy_router.post("/{kind}", status_code=201)
def create_taxonomy(
    kind: str,
    body: TaxonomyWrite,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> TaxonomyItemOut:
    item = taxonomy_service.create_item(
        db,
        user.id,
        kind,
        name=body.name,
        description=body.description,
        parent_id=body.parent_id,
        aliases=body.aliases,
        color=body.color,
        enabled=body.enabled,
        stop_word=body.stop_word,
    )
    db.commit()
    return TaxonomyItemOut(**item)


@private_router.get("")
def list_posts(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PostOut]:
    return [post_out(p) for p in service.list_posts(db, user.id)]


@private_router.post("", status_code=201)
def create_post(
    body: PostCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PostOut:
    post = service.create_post(
        db, user.id, title=body.title, markdown=body.markdown, source_refs=body.source_refs
    )
    db.commit()
    return post_out(post)


@private_router.get("/{post_id}")
def get_post(
    post_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PostOut:
    return post_detail_out(db, service.get_post(db, user.id, post_id))


@private_router.get("/{post_id}/visual-assets/{asset_id}.png")
def visual_asset(
    post_id: uuid.UUID,
    asset_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream a generated visual only to the owner of its post.

    The object key is derived from the checked post and UUID rather than taken
    from Markdown, so an article cannot use its image URL to read another
    user's storage object.
    """
    post = service.get_post(db, user.id, post_id)
    key = f"posts/{post.user_id}/visuals/{post.id}/{asset_id}.png"
    try:
        stream = get_storage().open_stream(key)
    except ObjectNotFoundError as exc:
        raise NotFoundError("Visual asset not found") from exc
    return StreamingResponse(
        stream,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )


@private_router.patch("/{post_id}")
def update_post(
    post_id: uuid.UUID,
    body: PostPatch,
    response: Response,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PostOut:
    post, warnings = service.patch_post(db, user.id, post_id, body)
    db.commit()
    if warnings:
        response.headers["X-Blog-Warnings"] = "; ".join(warnings)
    return post_detail_out(db, post)


@private_router.delete("/{post_id}", status_code=204)
def delete_post(
    post_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_post(db, user.id, post_id)
    db.commit()
    return Response(status_code=204)


@private_router.post("/{post_id}/generate", status_code=202)
def generate(
    post_id: uuid.UUID,
    body: GenerateBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    from app.modules.jobs import service as jobs_service

    post = service.get_post(db, user.id, post_id)
    job = jobs_service.create_job(
        db,
        user_id=user.id,
        job_type="blog.generate",
        entity_type="post",
        entity_id=post.id,
    )
    from app.services.outbox.publisher import append_event

    append_event(
        db,
        event_type="blog.generate",
        aggregate_type="post",
        aggregate_id=post.id,
        routing_key="llm.blog.generate",
        payload={
            "post_id": str(post.id),
            "scenario": body.scenario,
            "instruction": body.instruction,
            "job_id": str(job.id),
        },
        user_id=user.id,
    )
    db.commit()
    from app.modules.jobs.schemas import serialize_job

    return serialize_job(job).model_dump(mode="json")


@private_router.get("/{post_id}/revisions")
def list_revisions(
    post_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RevisionOut]:
    return [revision_out(r) for r in service.list_revisions(db, user.id, post_id)]


@private_router.get("/{post_id}/revisions/compare")
def compare_revisions(
    post_id: uuid.UUID,
    from_revision: uuid.UUID,
    to_revision: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return service.compare_revisions(db, user.id, post_id, from_revision, to_revision)


@private_router.get("/{post_id}/revisions/{revision_id}/diff")
def diff(
    post_id: uuid.UUID,
    revision_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return service.diff_revision(db, user.id, post_id, revision_id)


@private_router.post("/{post_id}/revisions/{revision_id}/apply")
def apply(
    post_id: uuid.UUID,
    revision_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PostOut:
    post = service.apply_revision(db, user.id, post_id, revision_id)
    db.commit()
    return post_out(post)


@private_router.post("/{post_id}/revisions/{revision_id}/restore")
def restore_revision(
    post_id: uuid.UUID,
    revision_id: uuid.UUID,
    body: RestoreRevisionBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PostOut:
    """Restore a past revision as a new user_edit revision (non-destructive)."""
    post = service.restore_revision(db, user.id, post_id, revision_id, current_version=body.version)
    db.commit()
    return post_out(post)


@private_router.post("/{post_id}/publish")
def publish(
    post_id: uuid.UUID,
    body: PublishBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PostOut:
    post = service.set_published(db, user.id, post_id, body.published, body.version)
    db.commit()
    return post_out(post)


# ------------------------------------------------------------------ public


@public_router.get("/posts/{slug}")
def public_post(slug: str, db: Session = Depends(get_db)) -> dict:
    post = service.get_public_post(db, slug)
    if post is None:
        raise NotFoundError("Post not found")
    return {
        "slug": post.slug,
        "title": post.title,
        "html": rendering.render_markdown(post.markdown),
        "excerpt": post.excerpt or rendering.build_excerpt(post.markdown),
        "published_at": post.published_at.isoformat() if post.published_at else None,
    }


@public_router.get("/rss.xml")
def public_rss(db: Session = Depends(get_db)) -> Response:
    posts = service.list_published(db)
    site_url = get_settings().app_base_url
    xml = rendering.render_rss(
        [
            {
                "slug": p.slug,
                "title": p.title,
                "excerpt": p.excerpt or rendering.build_excerpt(p.markdown),
                "published_at": p.published_at,
            }
            for p in posts
        ],
        site_url,
    )
    return Response(content=xml, media_type="application/rss+xml")
