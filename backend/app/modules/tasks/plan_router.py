"""Quick-add planning endpoints: analyze a line, then commit reviewed tasks."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.modules.tasks import plan_service
from app.modules.tasks import service as task_service
from app.modules.tasks.schemas import TaskOut
from app.services.llm.base import LLMError
from app.services.llm.schemas import VoiceTaskV1

router = APIRouter(prefix="/tasks", tags=["tasks"])


class QA(BaseModel):
    model_config = {"extra": "forbid"}
    question: str = Field(max_length=500)
    answer: str = Field(max_length=1000)


class AnalyzeBody(BaseModel):
    model_config = {"extra": "forbid"}
    text: str = Field(min_length=1, max_length=2000)
    answers: list[QA] = Field(default_factory=list, max_length=4)


class CommitBody(BaseModel):
    model_config = {"extra": "forbid"}
    tasks: list[VoiceTaskV1] = Field(min_length=1, max_length=20)


@router.post("/analyze")
def analyze(
    body: AnalyzeBody = Body(...),
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Analyze the quick-add text into a scheduling plan. Creates nothing."""
    answers = [(qa.question, qa.answer) for qa in body.answers]
    try:
        plan = plan_service.analyze(db, user.id, body.text, answers)
    except LLMError as exc:
        # The caller can still save the raw text as a plain todo (escape hatch).
        return {"tasks": [], "questions": [], "summary": "", "error": exc.code}
    return {
        "tasks": [t.model_dump(mode="json") for t in plan.tasks],
        "questions": plan.questions,
        "summary": plan.summary,
        "error": None,
    }


@router.post("/plan/commit", status_code=201)
def commit(
    body: CommitBody = Body(...),
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    created = plan_service.commit(db, user.id, body.tasks)
    db.commit()
    out = [
        TaskOut.from_model(t, task_service.get_tag_ids(db, t.id)).model_dump(mode="json")
        for t in created
    ]
    return {"created": out}
