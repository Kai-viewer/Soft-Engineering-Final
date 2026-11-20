from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.accounts.router import OptionalUser
from app.core.db import Db
from app.core.web import templates
from app.spaces.models import Room

router = APIRouter(tags=["spaces"])


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    floor: int
    capacity: int
    description: str
    panorama_path: str | None
    floor_plan_path: str | None
    map_x: float | None
    map_y: float | None


def list_rooms(db: Db):
    return db.scalars(select(Room).where(Room.active).order_by(Room.floor, Room.code)).all()


def get_room(room_id: int, db: Db) -> Room:
    room = db.get(Room, room_id)
    if room is None or not room.active:
        raise HTTPException(404, "找不到此空間")
    return room


router.add_api_route("/api/rooms", list_rooms, methods=["GET"], response_model=list[RoomRead])
router.add_api_route("/api/rooms/{room_id}", get_room, methods=["GET"], response_model=RoomRead)


@router.get("/spaces", include_in_schema=False)
def spaces_page(request: Request, db: Db, _user: OptionalUser):
    return templates.TemplateResponse(request, "spaces.html", {"rooms": list_rooms(db)})


@router.get("/spaces/{room_id}", include_in_schema=False)
def room_page(request: Request, room_id: int, db: Db, _user: OptionalUser):
    return templates.TemplateResponse(request, "room.html", {"room": get_room(room_id, db)})
