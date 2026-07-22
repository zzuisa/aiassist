"""Habit and habit-log models (US3).

Daily generated habit tasks are idempotent per (user, habit, local_date) via the
tasks table unique constraint; habit_logs are unique per (user, habit, local_date).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk


class Habit(Base, TimestampMixin):
    __tablename__ = "habits"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    recurrence_rule: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_time_local: Mapped[time | None] = mapped_column(Time)
    target_minutes: Mapped[int | None] = mapped_column(Integer)
    minimum_amount: Mapped[float | None] = mapped_column(Numeric(12, 3))
    unit: Mapped[str | None] = mapped_column(String(32))
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    auto_create_task: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_ai_adjustable: Mapped[bool] = mapped_column(nullable=False, default=True)
    active_from: Mapped[date | None] = mapped_column(Date)
    active_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status in ('active','paused','archived')", name="habit_status"),
    )


class HabitLog(Base):
    __tablename__ = "habit_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    habit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("habits.id", ondelete="CASCADE"), nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 3))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    skip_reason: Mapped[str | None] = mapped_column(String(24))
    skip_note: Mapped[str | None] = mapped_column(String(500))
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("status in ('completed','partial','skipped')", name="habit_log_status"),
        CheckConstraint(
            "skip_reason is null or skip_reason in "
            "('no_time','too_tired','forgot','unrealistic_plan','not_suitable','other')",
            name="habit_log_skip_reason",
        ),
        UniqueConstraint("user_id", "habit_id", "local_date", name="uq_habit_logs_user_habit_date"),
    )
