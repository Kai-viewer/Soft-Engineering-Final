from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator
from sqlalchemy import select

from app.accounts.models import User
from app.accounts.router import OptionalUser, require_role
from app.core.db import Db
from app.core.web import templates
from app.scheduling.models import Course
from app.spaces.models import Room

router = APIRouter(tags=["scheduling"])
Scheduler = Annotated[User, Depends(require_role("teacher", "admin"))]


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    teacher_id: int
    title: str
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    status: str

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def assume_utc_for_sqlite(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def visible_courses(db: Db, user: User):
    query = select(Course, Room.code).join(Room)
    if user.role != "admin":
        query = query.where(Course.teacher_id == user.id)
    return db.execute(query.order_by(Course.starts_at, Course.id)).all()


@router.get("/api/courses", response_model=list[CourseRead])
def courses_api(db: Db, user: Scheduler):
    return [course for course, _ in visible_courses(db, user)]


@router.get("/scheduling", include_in_schema=False)
def scheduling_page(request: Request, db: Db, user: OptionalUser):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user.role not in ("teacher", "admin"):
        return templates.TemplateResponse(request, "forbidden.html", status_code=403)
    return templates.TemplateResponse(request, "scheduling.html", {"rows": visible_courses(db, user)})
