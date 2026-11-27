"""空間查詢模組的查詢與工具函式（不含路由）。"""
import os
import re
import secrets
import struct
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.spaces.models import PLAN_BUILDING, FloorPlan, Room, RoomFacility

MODULE_DIR = Path(__file__).resolve().parent          # app/spaces/
STATIC_DIR = MODULE_DIR / "static"                    # 網址 /spaces/static/...
STATIC_URL = "/spaces/static/"
UPLOAD_URL = "/spaces/uploads/"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024


def upload_dir() -> Path:
    """上傳檔（360° 照片、平面圖）存放處，網址為 /spaces/uploads/...；可用環境變數 UPLOAD_DIR 改位置。"""
    path = Path(os.getenv("UPLOAD_DIR") or MODULE_DIR / "uploads")
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_file(root: Path, rel_path: str) -> Path | None:
    """回傳 root 底下的檔案路徑；路徑跳出 root（../）或檔案不存在時回傳 None"""
    root = root.resolve()
    full = (root / rel_path).resolve()
    return full if full.is_file() and root in full.parents else None


def floor_label(floor: int | None) -> str:
    if floor is None:
        return "-"
    return f"B{-floor}" if floor < 0 else f"{floor}F"


def parse_floor(text: str | None) -> int:
    """'2F' / '2' / '2樓' -> 2，'B1' -> -1；格式錯誤丟 ValueError"""
    t = (text or "").strip().upper().rstrip("F樓")
    m = re.fullmatch(r"B(\d)", t)
    if m:
        return -int(m.group(1))
    if re.fullmatch(r"-?\d{1,2}", t):
        return int(t)
    raise ValueError("樓層格式錯誤（例：2F、B1）")


def parse_facilities(text: str | None) -> list[tuple[str, int | None]]:
    """'投影機、無線麥克風*2' -> [('投影機', None), ('無線麥克風', 2)]（去除重複）"""
    out, seen = [], set()
    for item in re.split(r"[、,，;；\n]", text or ""):
        item = item.strip()
        if not item:
            continue
        m = re.match(r"^(.*?)\s*[\*＊×xX]\s*(\d+)$", item)
        name, qty = (m.group(1).strip(), int(m.group(2))) if m else (item, None)
        if name and name not in seen:
            seen.add(name)
            out.append((name[:100], qty or None))
    return out


def facilities_text(facilities) -> str:
    return "、".join(f.name + (f"*{f.quantity}" if f.quantity else "") for f in facilities)


# ------------------------------------------------------------ 查詢
def search_rooms(db: Session, f: dict, include_inactive: bool = False) -> list[Room]:
    query = select(Room).options(selectinload(Room.facilities))
    if not include_inactive:
        query = query.where(Room.active)
    q = (f.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        query = query.where(or_(
            Room.code.ilike(like), Room.name.ilike(like), Room.alias.ilike(like), Room.room_type.ilike(like),
            Room.manager.ilike(like), Room.location.ilike(like), Room.description.ilike(like),
            Room.facilities.any(RoomFacility.name.ilike(like)),
        ))
    if f.get("building"):
        query = query.where(Room.building == f["building"])
    if f.get("floor") is not None:
        query = query.where(Room.floor == f["floor"])
    if f.get("category"):
        query = query.where(Room.category == f["category"])
    if f.get("min_cap") is not None:
        query = query.where(Room.capacity >= f["min_cap"])
    if f.get("facility"):
        query = query.where(Room.facilities.any(RoomFacility.name == f["facility"]))
    if f.get("bookable"):
        query = query.where(Room.bookable)
    if f.get("pano"):
        query = query.where(Room.panorama_path.is_not(None))
    order = {
        "cap_desc": (Room.capacity.desc(), Room.code),
        "cap_asc": (Room.capacity.asc(), Room.code),
    }.get(f.get("sort"), ((Room.building != PLAN_BUILDING), Room.floor, Room.code))
    return list(db.scalars(query.order_by(*order)))


def common_facilities(db: Session, min_count: int = 2) -> list[str]:
    rows = db.execute(
        select(RoomFacility.name).join(Room).where(Room.active)
        .group_by(RoomFacility.name).having(func.count() >= min_count)
        .order_by(func.count().desc(), RoomFacility.name)
    )
    return [r[0] for r in rows]


def all_floors(db: Session, building: str | None = None) -> list[int]:
    query = select(Room.floor).where(Room.active).distinct()
    if building:
        query = query.where(Room.building == building)
    floors = set(db.scalars(query))
    if building == PLAN_BUILDING:
        floors |= set(db.scalars(select(FloorPlan.floor).where(FloorPlan.building == building)))
    return sorted(floors)


def rooms_on_floor(db: Session, floor: int, building: str = PLAN_BUILDING) -> list[Room]:
    return list(db.scalars(
        select(Room).options(selectinload(Room.facilities))
        .where(Room.active, Room.building == building, Room.floor == floor).order_by(Room.code)
    ))


def get_floor_plan(db: Session, floor: int, building: str = PLAN_BUILDING) -> FloorPlan | None:
    return db.scalar(select(FloorPlan).where(FloorPlan.building == building, FloorPlan.floor == floor))


def sync_floor_plan_paths(db: Session, floor: int, building: str = PLAN_BUILDING) -> None:
    """rooms.floor_plan_path 跟著樓層平面圖更新，讓其他模組也能直接顯示。"""
    plan = get_floor_plan(db, floor, building)
    for room in db.scalars(select(Room).where(Room.building == building, Room.floor == floor)):
        room.floor_plan_path = plan.image_path if plan else None


# ------------------------------------------------------------ 圖片上傳
def image_info(data: bytes):
    """依檔頭判斷圖片：回傳 (副檔名, 寬, 高)；不是 JPG/PNG 回傳 None"""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 24:
        w, h = struct.unpack(">II", data[16:24])
        return "png", w, h
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01, 0xFF) or 0xD0 <= marker <= 0xD7:
                i += 1 if marker == 0xFF else 2
                continue
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpg", w, h
            i += 2 + seg_len
    return None


def read_upload(upload) -> bytes | None:
    """讀取 UploadFile；沒選檔案回傳 None，超過上限丟 ValueError"""
    if upload is None or not getattr(upload, "filename", None):
        return None
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"檔案太大（上限 {MAX_UPLOAD_BYTES // 1024 // 1024}MB）")
    return data or None


def save_upload(data: bytes, subdir: str, prefix: str) -> tuple[str, int, int]:
    """存檔並回傳 (網址路徑, 寬, 高)"""
    info = image_info(data)
    if not info:
        raise ValueError("只接受 JPG 或 PNG 圖片")
    ext, w, h = info
    folder = upload_dir() / subdir
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}_{secrets.token_hex(4)}.{ext}"
    (folder / name).write_bytes(data)
    return f"{UPLOAD_URL}{subdir}/{name}", w, h


def delete_upload(url_path: str | None) -> None:
    """只刪除上傳區（/spaces/uploads/）的檔案；內建的官方平面圖（/spaces/static/）不會被刪"""
    if not url_path or not url_path.startswith(UPLOAD_URL):
        return
    full = safe_file(upload_dir(), url_path.removeprefix(UPLOAD_URL))
    if full:
        full.unlink()
