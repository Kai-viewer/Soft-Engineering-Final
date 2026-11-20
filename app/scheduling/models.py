from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_courses_interval"),
        CheckConstraint("status IN ('requested', 'confirmed')", name="ck_courses_status"),
        Index("ix_courses_room_starts", "room_id", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default="requested")
