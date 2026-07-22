"""Task model (task/fixed_event/habit_task/reminder/note) and task-tag join.

Fixed events cannot be AI-adjustable. Habit tasks are unique per (habit, date);
plain recurring instances are unique per (recurrence_parent, occurrence_date).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk

TASK_TYPES = ("task", "fixed_event", "habit_task", "reminder", "note")
TASK_STATUSES = ("todo", "in_progress", "completed", "cancelled")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(24), nullable=False, default="task")
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="todo")
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    actual_minutes: Mapped[int | None] = mapped_column(Integer)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    is_fixed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_ai_adjustable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_splittable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    energy_level: Mapped[str | None] = mapped_column(String(16))
    recurrence_rule: Mapped[str | None] = mapped_column(Text)
    recurrence_parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    occurrence_date: Mapped[date | None] = mapped_column(Date)
    source_type: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    habit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    habit_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "type in ('task','fixed_event','habit_task','reminder','note')", name="task_type"
        ),
        CheckConstraint(
            "status in ('todo','in_progress','completed','cancelled')", name="task_status"
        ),
        CheckConstraint("priority >= 0 and priority <= 4", name="task_priority"),
        CheckConstraint("importance >= 0 and importance <= 4", name="task_importance"),
        CheckConstraint("not (is_fixed and is_ai_adjustable)", name="task_fixed_not_ai_adjustable"),
        CheckConstraint(
            "due_at is null or start_at is null or due_at >= start_at", name="task_due_after_start"
        ),
        UniqueConstraint("user_id", "habit_id", "habit_date", name="uq_tasks_user_habit_date"),
        UniqueConstraint(
            "user_id",
            "recurrence_parent_id",
            "occurrence_date",
            name="uq_tasks_user_recurrence_occurrence",
        ),
        Index("ix_tasks_user_id_status_due_at", "user_id", "status", "due_at"),
        Index("ix_tasks_user_id_start_at", "user_id", "start_at"),
        Index("ix_tasks_user_id_deleted_at", "user_id", "deleted_at"),
    )


class TaskTag(Base):
    __tablename__ = "task_tags"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
