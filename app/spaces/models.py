from sqlalchemy import Boolean, CheckConstraint, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_rooms_capacity"),
        CheckConstraint(
            "(map_x IS NULL AND map_y IS NULL) OR "
            "(map_x IS NOT NULL AND map_y IS NOT NULL AND "
            "map_x BETWEEN 0 AND 100 AND map_y BETWEEN 0 AND 100)",
            name="ck_rooms_map_coordinates",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    floor: Mapped[int]
    capacity: Mapped[int]
    description: Mapped[str] = mapped_column(Text, server_default="")
    panorama_path: Mapped[str | None] = mapped_column(String(255))
    floor_plan_path: Mapped[str | None] = mapped_column(String(255))
    map_x: Mapped[float | None]
    map_y: Mapped[float | None]
    active: Mapped[bool] = mapped_column(Boolean, server_default=true())
