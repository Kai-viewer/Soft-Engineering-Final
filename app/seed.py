import os
from datetime import datetime, timedelta, timezone
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.accounts.router import password_hasher
from app.bookings.models import Booking, BookingItem, Equipment
from app.core.db import make_engine
from app.core.web import TAIPEI
from app.scheduling.models import Course
from app.spaces.models import Room


def seed(engine, password: str) -> None:
    if os.getenv("DEMO_MODE", "").lower() != "true":
        raise RuntimeError("Enable DEMO_MODE only on a local development database.")
    local_database = engine.url.host in {None, "localhost", "127.0.0.1", "::1"}
    if len(password) < 12 and not (password == "123" and local_database):
        raise ValueError("Use at least 12 characters unless using the local demo password.")

    with Session(engine) as db, db.begin():
        users = {}
        digest = password_hasher.hash(password)
        for role, name in (("member", "測試使用者"), ("teacher", "測試教師"), ("admin", "測試管理員")):
            email = f"{role}@example.test"
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(email=email, display_name=name, role=role, status="approved",
                            password_hash=digest)
                db.add(user)
            users[role] = user

        rooms = {}
        for code, name, floor, capacity in (
            ("DEMO-301", "三樓示範教室", 3, 48),
            ("DEMO-402", "四樓示範研討室", 4, 20),
        ):
            room = db.scalar(select(Room).where(Room.code == code))
            if room is None:
                room = Room(code=code, name=name, floor=floor, capacity=capacity)
                db.add(room)
            rooms[code] = room

        equipment = {}
        for code, name in (("DEMO-KEY", "教室鑰匙"), ("DEMO-POINTER", "投影筆"), ("DEMO-LAPTOP", "筆電")):
            item = db.scalar(select(Equipment).where(Equipment.code == code))
            if item is None:
                item = Equipment(code=code, name=name)
                db.add(item)
            equipment[code] = item
        db.flush()

        start = (datetime.now(TAIPEI) + timedelta(days=1)).replace(
            hour=10, minute=0, second=0, microsecond=0
        ).astimezone(timezone.utc)
        end = start + timedelta(hours=1)
        member = users["member"]
        teacher = users["teacher"]
        room = rooms["DEMO-301"]
        if db.scalar(select(Booking.id).where(Booking.requester_id == member.id).limit(1)) is None:
            booking = Booking(requester_id=member.id, room_id=room.id, starts_at=start, ends_at=end)
            db.add(booking)
            db.flush()
            db.add_all(
                BookingItem(booking_id=booking.id, equipment_id=equipment[code].id)
                for code in ("DEMO-KEY", "DEMO-POINTER")
            )
        if db.scalar(select(Course.id).where(Course.teacher_id == teacher.id).limit(1)) is None:
            db.add(Course(title="軟體工程", room_id=room.id, teacher_id=teacher.id,
                          starts_at=start + timedelta(hours=2), ends_at=end + timedelta(hours=2)))


def main() -> None:
    engine = make_engine()
    try:
        password = os.getenv("DEMO_PASSWORD") or getpass("Password for the three demo users: ")
        seed(engine, password)
        print("Demo data ready: member@example.test, teacher@example.test, admin@example.test")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
