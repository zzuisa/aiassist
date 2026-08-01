"""AI optimization endpoints (spec 005, US3, T072).

``POST /posts/{post_id}/optimize`` submits work bound to the current revision and
returns the Job (202). ``GET /blog/ai/runs/{run_id}`` exposes run detail, and
``POST /blog/ai/runs/{run_id}/cancel`` requests cancellation. Applying a candidate
is a separate flow (US4).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.models.blog import PostAIRun
from app.modules.jobs.schemas import serialize_job
from app.modules.posts import ai_service
from app.modules.posts.schemas import CandidateDecisionBody, OptimizeBody

# Optimize lives under /posts to match the contract; a separate router keeps the
# AI run endpoints under /blog/ai.
optimize_router = APIRouter(prefix="/posts", tags=["blog-ai"])
ai_router = APIRouter(prefix="/blog/ai", tags=["blog-ai"])


def _run_out(run: PostAIRun) -> dict:
    return {
        "id": str(run.id),
        "post_id": str(run.post_id),
        "job_id": str(run.async_job_id),
        "optimization_type": run.optimization_type,
        "content_class": run.content_class,
        "skill_version_id": str(run.skill_version_id),
        "provider_key": run.provider_key,
        "model_key": run.model_key,
        "ai_schema_version": run.ai_schema_version,
        "input_hash": run.input_hash,
        "outcome": run.outcome,
        "candidate_id": str(run.candidate_id) if run.candidate_id else None,
        "validation_summary": run.validation_summary_json,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@optimize_router.post("/{post_id}/optimize", status_code=202)
def optimize(
    post_id: uuid.UUID,
    body: OptimizeBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    job, _run, _dup = ai_service.submit_optimization(
        db,
        user.id,
        post_id,
        post_version=body.post_version,
        optimization_type=body.optimization_type,
        scope=body.scope,
        selected_fields=body.selected_fields,
        skill_id=body.skill_id,
        provider_key=body.provider_key,
        model_key=body.model_key,
        instruction=body.instruction,
    )
    db.commit()
    return serialize_job(job).model_dump(mode="json")


@ai_router.get("/runs/{run_id}")
def get_run(
    run_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return _run_out(ai_service.get_run(db, user.id, run_id))


@ai_router.post("/runs/{run_id}/cancel", status_code=202)
def cancel_run(
    run_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    job = ai_service.cancel_run(db, user.id, run_id)
    db.commit()
    return serialize_job(job).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Candidate review + decision (spec 005, US4, T089)
# ---------------------------------------------------------------------------


@optimize_router.get("/{post_id}/candidates")
def list_candidates(
    post_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        ai_service.serialize_candidate(c) for c in ai_service.list_candidates(db, user.id, post_id)
    ]


@ai_router.get("/candidates/{candidate_id}")
def get_candidate(
    candidate_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Three-way (base/current/candidate) comparison for review."""
    return ai_service.compare_candidate(db, user.id, candidate_id)


@ai_router.post("/candidates/{candidate_id}/decide")
def decide_candidate(
    candidate_id: uuid.UUID,
    body: CandidateDecisionBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    result = ai_service.decide_candidate(
        db,
        user.id,
        candidate_id,
        action=body.action,
        selected_fields=body.selected_fields,
        current_version=body.post_version,
    )
    db.commit()
    return result
