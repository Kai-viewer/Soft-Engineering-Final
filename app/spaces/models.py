from sqlalchemy import Boolean, CheckConstraint, ForeignKey, SmallInteger, String, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

CATEGORIES = {
    "classroom": "教室",
    "meeting_room": "會議室",
    "seminar_room": "研討室",
    "hall": "會議廳",
    "lounge": "交誼空間",
    "office": "辦公室",
    "research_room": "研究室",
    "other": "其他",
}
BUILDINGS = ("管理學院", "教育學院")
PLAN_BUILDING = "管理學院"          # 平面圖只做管理學院大樓


class Room(Base):
    """共用教室資料表：預約與排課模組以 rooms.id 為外鍵。"""
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
    code: Mapped[str] = mapped_column(String(32), unique=True)        # 管228、管B15、教A001
    name: Mapped[str] = mapped_column(String(100))                    # 廳名或類型，如「賈伯斯廳」
    floor: Mapped[int]                                                # 地下室為負數（B1 = -1）
    capacity: Mapped[int]
    description: Mapped[str] = mapped_column(Text, server_default="")
    panorama_path: Mapped[str | None] = mapped_column(String(255))    # 360° 全景照片網址路徑
    floor_plan_path: Mapped[str | None] = mapped_column(String(255))  # 所在樓層平面圖網址路徑
    map_x: Mapped[float | None]                                       # 平面圖位置（0～100，%）
    map_y: Mapped[float | None]
    active: Mapped[bool] = mapped_column(Boolean, server_default=true())   # False＝已停用（不再顯示）

    # 空間查詢模組新增的欄位（migrations/versions/0002_spaces_details.py）
    # 只用一般欄位（不加外鍵 / CHECK），SQLite 上 ADD / DROP COLUMN 不必重建資料表；
    # category、borrow_method 的合法值由 app/spaces/router.py 檢查
    building: Mapped[str] = mapped_column(String(20), server_default=PLAN_BUILDING)
    room_type: Mapped[str | None] = mapped_column(String(50))         # 網站原始類型，如「個案階梯教室」
    alias: Mapped[str | None] = mapped_column(String(50))             # 廳名，如「賈伯斯廳」
    category: Mapped[str] = mapped_column(String(20), server_default="classroom")   # 見 CATEGORIES
    bookable: Mapped[bool] = mapped_column(Boolean, server_default=true())
    manager: Mapped[str | None] = mapped_column(String(100))          # 管理單位
    borrow_method: Mapped[str | None] = mapped_column(String(30))     # borrow_methods.code
    location: Mapped[str | None] = mapped_column(String(100))
    usage_note: Mapped[str | None] = mapped_column(Text)              # 使用方式
    note: Mapped[str | None] = mapped_column(Text)                    # 備註
    source_url: Mapped[str | None] = mapped_column(String(255))

    facilities: Mapped[list["RoomFacility"]] = relationship(
        back_populates="room", cascade="all, delete-orphan", order_by="RoomFacility.id"
    )


class RoomFacility(Base):
    """教室固定設備（投影機、麥克風…），與預約模組可借出的 equipment 不同。"""
    __tablename__ = "room_facilities"
    __table_args__ = (UniqueConstraint("room_id", "name", name="uq_room_facilities_room_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int | None]

    room: Mapped[Room] = relationship(back_populates="facilities")


class BorrowMethod(Base):
    """各管理單位的借用方式（依國企系網站「管院教室借用方法」）。"""
    __tablename__ = "borrow_methods"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default="0")


class FloorPlan(Base):
    """各樓層平面圖（預設為管理學院院辦的官方平面圖）。"""
    __tablename__ = "floor_plans"
    __table_args__ = (UniqueConstraint("building", "floor", name="uq_floor_plans_building_floor"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    building: Mapped[str] = mapped_column(String(20))
    floor: Mapped[int]
    image_path: Mapped[str] = mapped_column(String(255))   # 網址路徑，如 /spaces/static/floorplans/2F.png
    width: Mapped[int]
    height: Mapped[int]
