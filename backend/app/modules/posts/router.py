"""Post endpoints: private CRUD/revisions/publish + public post/RSS."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models.posts import Post
from app.modules.posts import rendering, service

private_router = APIRouter(prefix="/posts", tags=["posts"])
public_router = APIRouter(prefix="/public", tags=["public"])


class PostCreate(BaseModel):
    model_config = {"extra": "forbid"}
    title: str = Field(min_length=1, max_length=240)
    markdown: str = Field(max_length=200000)
    source_refs: list[dict] = Field(default_factory=list)
    version: int | None = None


class GenerateBody(BaseModel):
    model_config = {"extra": "forbid"}
    scenario: str = Field(pattern="^(generate_blog|optimize_blog|translate_blog)$")
    source_refs: list[dict] = Field(default_factory=list, max_length=50)
    instruction: str | None = Field(default=None, max_length=2000)


class PublishBody(BaseModel):
    model_config = {"extra": "forbid"}
    published: bool
    version: int


def _post_out(p: Post) -> dict:
    return {
        "id": str(p.id),
        "title": p.title,
        "markdown": p.markdown,
        "status": p.status,
        "slug": p.slug,
        "version": p.version,
        "current_revision_id": str(p.current_revision_id) if p.current_revision_id else None,
        "created_at": p.created_at.isoformat(),
        "published_at": p.published_at.isoformat() if p.published_at else None,
    }


@private_router.get("")
def list_posts(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    return [_post_out(p) for p in service.list_posts(db, user.id)]


@private_router.post("", status_code=201)
def create_post(
    body: PostCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    post = service.create_post(
        db, user.id, title=body.title, markdown=body.markdown, source_refs=body.source_refs
    )
    db.commit()
    return _post_out(post)


@private_router.get("/{post_id}")
def get_post(
    post_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return _post_out(service.get_post(db, user.id, post_id))


@private_router.patch("/{post_id}")
def update_post(
    post_id: uuid.UUID,
    body: PostCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    post = service.save_user_revision(
        db, user.id, post_id, title=body.title, markdown=body.markdown, version=body.version or 1
    )
    db.commit()
    return _post_out(post)


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
) -> dict:
    post = service.apply_revision(db, user.id, post_id, revision_id)
    db.commit()
    return _post_out(post)


@private_router.post("/{post_id}/publish")
def publish(
    post_id: uuid.UUID,
    body: PublishBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    post = service.set_published(db, user.id, post_id, body.published, body.version)
    db.commit()
    return _post_out(post)


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
