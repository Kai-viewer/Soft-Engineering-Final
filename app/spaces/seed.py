"""匯入管院空間資料：爬蟲結果（data/spaces.json）、借用方式、官方樓層平面圖與教室位置。

    uv run python -m app.spaces.seed

與 app/seed.py 相同，重複執行只會補上缺少的資料，不會覆蓋管理員在後台改過的內容。
app/seed.py（測試帳號）執行時也會順便呼叫這裡。
"""
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import make_engine
from app.spaces.models import BUILDINGS, PLAN_BUILDING, BorrowMethod, FloorPlan, Room, RoomFacility

DATA_DIR = Path(__file__).resolve().parent / "data"

BORROW_METHOD_NAMES = {
    "ibs_system": "國企系借教室系統",
    "college_form": "管院場所借用申請單",
    "contact_secretary": "洽管院祕書",
    "contact_department": "洽管理系所系辦",
    "not_bookable": "不開放借用",
    "unknown": "未註明",
}


def _load(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def seed_spaces(engine) -> dict:
    """回傳 {'rooms_added': n, 'skipped': [沒有人數而略過的空間]}"""
    spaces = _load("spaces.json")["spaces"]
    methods = _load("booking_rules.json").get("methods", {})
    plans = _load("floorplans.json")
    positions = {code: xy for info in plans["floors"].values() for code, xy in info["rooms"].items()}
    plan_paths = {int(floor): info["image"] for floor, info in plans["floors"].items()}

    added, skipped = 0, []
    with Session(engine) as db, db.begin():
        for order, (code, name) in enumerate(BORROW_METHOD_NAMES.items()):
            if db.get(BorrowMethod, code) is None:
                m = methods.get(code, {})
                db.add(BorrowMethod(code=code, name=name, description=m.get("description") or name,
                                    url=m.get("url"), sort_order=order))

        for floor, info in plans["floors"].items():
            floor = int(floor)
            if db.scalar(select(FloorPlan.id).where(FloorPlan.building == PLAN_BUILDING,
                                                    FloorPlan.floor == floor)) is None:
                db.add(FloorPlan(building=PLAN_BUILDING, floor=floor, image_path=info["image"],
                                 width=plans["width"], height=plans["height"]))
        db.flush()

        existing = set(db.scalars(select(Room.code)))
        for s in spaces:
            if s["room_code"] in existing:
                continue
            if not s["capacity"] or s["floor"] is None:
                # rooms.capacity 必須 > 0（預約模組依賴），網站沒寫人數的辦公室不匯入
                skipped.append(s["room_code"])
                continue
            building = s["building"] if s["building"] in BUILDINGS else PLAN_BUILDING
            xy = positions.get(s["room_code"]) if building == PLAN_BUILDING else None
            room = Room(
                code=s["room_code"],
                name=s["alias"] or s["room_type"] or s["room_code"],
                floor=s["floor"],
                capacity=s["capacity"],
                description=s["description"] or "",
                building=building,
                room_type=s["room_type"],
                alias=s["alias"],
                category=s["category"],
                bookable=s["bookable"],
                manager=s["manager"],
                borrow_method=s["booking_method"],
                location=s["location"],
                usage_note=s["usage"],
                note=s["note"],
                source_url=s["source_url"],
                map_x=xy[0] if xy else None,
                map_y=xy[1] if xy else None,
                floor_plan_path=plan_paths.get(s["floor"]) if building == PLAN_BUILDING else None,
            )
            seen = set()
            for e in s["equipment"]:
                if e["name"] not in seen:
                    seen.add(e["name"])
                    room.facilities.append(RoomFacility(name=e["name"], quantity=e["qty"]))
            db.add(room)
            added += 1
    return {"rooms_added": added, "skipped": skipped}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows 主控台印中文教室編號
    engine = make_engine()
    try:
        result = seed_spaces(engine)
        print(f"Spaces ready: {result['rooms_added']} rooms added.")
        if result["skipped"]:
            print("Skipped (no capacity on the source site): " + ", ".join(result["skipped"]))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
