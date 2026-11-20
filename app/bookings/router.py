from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator
from sqlalchemy import select

from app.accounts.models import User
from app.accounts.router import CurrentUser, OptionalUser
from app.bookings.models import Booking
from app.core.db import Db
from app.core.web import templates
from app.spaces.models import Room

router = APIRouter(tags=["bookings"])


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    requester_id: int
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    status: str
    review_note: str | None

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def assume_utc_for_sqlite(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def visible_bookings(db: Db, user: User):
    query = select(Booking, Room.code).join(Room)
    if user.role != "admin":
        query = query.where(Booking.requester_id == user.id)
    return db.execute(query.order_by(Booking.starts_at, Booking.id)).all()


@router.get("/api/bookings", response_model=list[BookingRead])
def bookings_api(db: Db, user: CurrentUser):
    return [booking for booking, _ in visible_bookings(db, user)]


@router.get("/bookings", include_in_schema=False)
def bookings_page(request: Request, db: Db, user: OptionalUser):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "bookings.html", {"rows": visible_bookings(db, user)})
