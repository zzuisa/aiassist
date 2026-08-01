"""Quick-add planning: enqueue background analysis, answer questions, or skip."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.core.observability import get_logger
from app.db.session import get_db
from app.modules.jobs import service as jobs_service
from app.modules.tasks import plan_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


class PlanBody(BaseModel):
    model_config = {"extra": "forbid"}
    text: str = Field(min_length=1, max_length=2000)


class QA(BaseModel):
    model_config = {"extra": "forbid"}
    question: str = Field(max_length=500)
    answer: str = Field(max_length=1000)


class AnswerBody(BaseModel):
    model_config = {"extra": "forbid"}
    answers: list[QA] = Field(min_length=1, max_length=4)


def _enqueue(job_id: uuid.UUID) -> None:
    try:
        from app.workers.tasks.plan import process_plan

        process_plan.delay(str(job_id))
    except Exception:
        get_logger("plan").warning("plan_enqueue_failed")


@router.post("/plan", status_code=202)
def create_plan(
    body: PlanBody = Body(...),
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """立即加入后台分析队列；不阻塞，不即时创建任务。"""
    job = plan_service.create_plan_job(db, user.id, body.text)
    db.commit()
    _enqueue(job.id)
    return {"job_id": str(job.id), "status": job.status}


@router.get("/plan/{job_id}")
def get_plan(
    job_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    job = jobs_service.get_owned_job(db, user.id, job_id)
    data = job.result_json or {}
    return {
        "job_id": str(job.id),
        "status": job.status,
        "questions": data.get("questions", []),
        "tasks": data.get("tasks", []),
        "summary": data.get("summary", ""),
        "created": data.get("created"),
    }


@router.post("/plan/{job_id}/answer", status_code=202)
def answer_plan(
    job_id: uuid.UUID,
    body: AnswerBody = Body(...),
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    answers = [(qa.question, qa.answer) for qa in body.answers]
    job = plan_service.answer_plan(db, user.id, job_id, answers)
    db.commit()
    _enqueue(job.id)
    return {"job_id": str(job.id), "status": job.status}


@router.post("/plan/{job_id}/skip", status_code=201)
def skip_plan(
    job_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    job = plan_service.skip_plan(db, user.id, job_id)
    db.commit()
    return {"job_id": str(job.id), "status": job.status}
