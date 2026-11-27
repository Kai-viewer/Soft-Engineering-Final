"""空間查詢模組（負責人 A）：教室查詢與詳情、管理員教室增刪改、樓層標記、360° 檢視。

本模組的檔案全部放在 app/spaces/ 內：
  templates/spaces/   頁面樣板（繼承共用的 app/templates/base.html）
  static/             CSS、JS、官方樓層平面圖、Google 地圖截圖（網址 /spaces/static/...）
  uploads/            管理員上傳的 360° 照片與平面圖（網址 /spaces/uploads/...，不進 Git）
  data/               爬蟲資料與平面圖座標，由 seed.py 匯入
"""
import secrets
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.accounts.models import User
from app.accounts.router import OptionalUser
from app.core.db import Db
from app.core.web import APP_DIR
from app.spaces.floorplan import BUILDING_MAP, build_plan, build_site_map, is_official_plan
from app.spaces.models import BUILDINGS, CATEGORIES, PLAN_BUILDING, BorrowMethod, FloorPlan, Room, RoomFacility
from app.spaces.service import (MODULE_DIR, STATIC_DIR, STATIC_URL, all_floors, common_facilities, delete_upload,
                                facilities_text, floor_label, get_floor_plan, image_info, parse_facilities,
                                parse_floor, read_upload, rooms_on_floor, safe_file, save_upload, search_rooms,
                                sync_floor_plan_paths, upload_dir)

router = APIRouter(tags=["spaces"])

# 本模組自己的樣板環境：先找 app/spaces/templates，再找共用的 app/templates（base.html）
templates = Jinja2Templates(directory=[MODULE_DIR / "templates", APP_DIR / "templates"])
templates.env.filters["floor"] = floor_label
templates.env.filters["category"] = lambda c: CATEGORIES.get(c, c)


def asset(name: str) -> str:
    """CSS / JS 網址帶上檔案修改時間，檔案一改瀏覽器就會抓新版（不會卡在舊快取）"""
    return f"{STATIC_URL}{name}?v={int((STATIC_DIR / name).stat().st_mtime)}"


templates.env.globals.update(CATEGORIES=CATEGORIES, asset=asset)

OFFICIAL_PLAN_URL = "https://cm.ncnu.edu.tw/p/406-1066-39100,r1554.php?Lang=zh-tw"


# ================================================================ 共用小工具（只在本模組使用）
def redirect_with_message(url: str, message: str, kind: str = "success") -> RedirectResponse:
    """導向後在頁面上方顯示訊息（spaces/_layout.html 讀取 msg、msg_type）"""
    sep = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{sep}msg_type={quote(kind)}&msg={quote(message)}", status_code=303)


def admin_page(user: OptionalUser) -> User:
    """管理頁面用：未登入導向 /login，非管理員導回空間查詢（瀏覽器會直接跟著 303 跳轉）"""
    if user is None:
        raise HTTPException(303, "請先登入", headers={"Location": "/login"})
    if user.role != "admin":
        location = f"/rooms?msg_type=warning&msg={quote('此頁面僅限管理員使用。')}"
        raise HTTPException(303, "權限不足", headers={"Location": location})
    return user


AdminPage = Annotated[User, Depends(admin_page)]


def verify_csrf(request: Request, csrf_token: str) -> None:
    """比對表單的 csrf_token 與目前 session（由共用的 optional_user 放在 request.state）"""
    expected = getattr(request.state, "csrf_token", "")
    if not expected or not secrets.compare_digest(csrf_token.encode(), expected.encode()):
        raise HTTPException(403, "登入已失效或表單驗證失敗")


def _is_admin(user: User | None) -> bool:
    return user is not None and user.role == "admin"


def _to_management() -> RedirectResponse:
    """管理員不使用前台的查詢頁與平面圖頁，一律導向教室管理"""
    return RedirectResponse("/admin/rooms", status_code=303)


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def _filters(q, building, floor, category, min_cap, facility, sort, bookable, pano) -> dict:
    return {
        "q": q.strip(),
        "building": building if building in BUILDINGS else "",
        "floor": _int_or_none(floor),
        "category": category if category in CATEGORIES else "",
        "min_cap": _int_or_none(min_cap),
        "facility": facility,
        "sort": sort,
        "bookable": bookable == "1",
        "pano": pano == "1",
    }


def room_json(room: Room) -> dict:
    return {
        "id": room.id, "code": room.code, "name": room.name, "alias": room.alias,
        "building": room.building, "floor": room.floor, "floor_label": floor_label(room.floor),
        "category": room.category, "room_type": room.room_type, "capacity": room.capacity,
        "bookable": room.bookable, "manager": room.manager, "location": room.location,
        "facilities": [{"name": f.name, "quantity": f.quantity} for f in room.facilities],
        "panorama_path": room.panorama_path, "floor_plan_path": room.floor_plan_path,
        "map_x": room.map_x, "map_y": room.map_y, "url": f"/rooms/{room.id}",
    }


def _find_room(db, room_id: int, include_inactive=False) -> Room | None:
    room = db.scalar(select(Room).options(selectinload(Room.facilities)).where(Room.id == room_id))
    if room is None or (not room.active and not include_inactive):
        return None
    return room


def _get_room(db, room_id: int, include_inactive=False) -> Room:
    room = _find_room(db, room_id, include_inactive)
    if room is None:
        raise HTTPException(404, "找不到這間教室")
    return room


# ================================================================ 本模組的靜態檔與上傳檔
@router.get("/spaces/static/{path:path}", include_in_schema=False)
def spaces_static(path: str):
    full = safe_file(STATIC_DIR, path)
    if full is None:
        raise HTTPException(404, "找不到檔案")
    return FileResponse(full, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/spaces/uploads/{path:path}", include_in_schema=False)
def spaces_uploads(path: str):
    full = safe_file(upload_dir(), path)
    if full is None:
        raise HTTPException(404, "找不到檔案")
    return FileResponse(full, headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"})


# ================================================================ 前台（免登入）
@router.get("/rooms", include_in_schema=False)
def room_search(request: Request, db: Db, user: OptionalUser, q: str = "", building: str = "", floor: str = "",
                category: str = "", min_cap: str = "", facility: str = "", sort: str = "room",
                bookable: str = "", pano: str = ""):
    if _is_admin(user):
        return _to_management()
    f = _filters(q, building, floor, category, min_cap, facility, sort, bookable, pano)
    return templates.TemplateResponse(request, "spaces/search.html", {
        "rooms": search_rooms(db, f),
        "total": db.scalar(select(func.count()).select_from(Room).where(Room.active)),
        "f": f,
        "buildings": BUILDINGS,
        "floors": all_floors(db),
        "facility_names": common_facilities(db),
    })


@router.get("/rooms/floorplan", include_in_schema=False)
def floorplan_page(request: Request, db: Db, user: OptionalUser, floor: str = ""):
    if _is_admin(user):
        return _to_management()
    floors = all_floors(db, PLAN_BUILDING)
    current = _int_or_none(floor)
    if current not in floors:
        current = 2 if 2 in floors else (floors[0] if floors else 1)
    rooms = rooms_on_floor(db, current)
    plan_row = get_floor_plan(db, current)
    return templates.TemplateResponse(request, "spaces/floorplan.html", {
        "floors": floors, "current": current, "rooms": rooms,
        "plan": build_plan(rooms, plan_row), "has_image": plan_row is not None,
        "is_official": is_official_plan(plan_row),
        "official_url": OFFICIAL_PLAN_URL,
        # Google 地圖截圖：標出本層每間教室在大樓裡的大約位置
        "site_map": build_site_map(rooms, plan_row),
        "map_info": BUILDING_MAP,
    })


@router.get("/rooms/{room_id}", include_in_schema=False)
def room_detail(request: Request, db: Db, _user: OptionalUser, room_id: int):
    room = _find_room(db, room_id)
    if room is None:
        return templates.TemplateResponse(request, "spaces/not_found.html", {}, status_code=404)
    plan = None
    if room.building == PLAN_BUILDING:
        plan = build_plan(rooms_on_floor(db, room.floor), get_floor_plan(db, room.floor), highlight_id=room.id)
        if not any(d["id"] == room.id for d in plan["dots"]):
            plan = None
    method = db.get(BorrowMethod, room.borrow_method) if room.borrow_method else None
    return templates.TemplateResponse(request, "spaces/detail.html", {"room": room, "method": method, "plan": plan})


# ================================================================ JSON API（Swagger：/docs）
@router.get("/api/rooms")
def api_rooms(db: Db, q: str = "", building: str = "", floor: str = "", category: str = "",
              min_cap: str = "", facility: str = "", sort: str = "room", bookable: str = "", pano: str = ""):
    """查詢教室（不需登入）。預約、排課模組可用來取得 rooms.id 與教室資訊。"""
    f = _filters(q, building, floor, category, min_cap, facility, sort, bookable, pano)
    return [room_json(r) for r in search_rooms(db, f)]


@router.get("/api/rooms/{room_id}")
def api_room(db: Db, room_id: int):
    return room_json(_get_room(db, room_id))


# ================================================================ 管理員：教室增刪改
@router.get("/admin/rooms", include_in_schema=False)
def admin_rooms(request: Request, db: Db, _admin: AdminPage, q: str = ""):
    return templates.TemplateResponse(request, "spaces/admin_rooms.html", {
        "rooms": search_rooms(db, {"q": q}, include_inactive=True), "q": q,
    })


def room_form_fields(
    code: Annotated[str, Form(max_length=32)] = "",
    name: Annotated[str, Form(max_length=100)] = "",
    alias: Annotated[str, Form(max_length=50)] = "",
    building: Annotated[str, Form(max_length=20)] = PLAN_BUILDING,
    floor: Annotated[str, Form(max_length=5)] = "",
    room_type: Annotated[str, Form(max_length=50)] = "",
    category: Annotated[str, Form(max_length=20)] = "classroom",
    capacity: Annotated[str, Form(max_length=6)] = "",
    bookable: Annotated[str, Form(max_length=1)] = "",
    manager: Annotated[str, Form(max_length=100)] = "",
    borrow_method: Annotated[str, Form(max_length=30)] = "",
    location: Annotated[str, Form(max_length=100)] = "",
    description: Annotated[str, Form(max_length=5000)] = "",
    usage_note: Annotated[str, Form(max_length=2000)] = "",
    note: Annotated[str, Form(max_length=2000)] = "",
    facilities: Annotated[str, Form(max_length=2000)] = "",
    remove_panorama: Annotated[str, Form(max_length=1)] = "",
    csrf_token: Annotated[str, Form()] = "",
) -> dict:
    return dict(locals())


RoomForm = Annotated[dict, Depends(room_form_fields)]
PanoramaFile = Annotated[UploadFile | None, File()]


def _form_page(request, db, room: dict, facilities: str, is_new: bool, errors=None, status=200):
    methods = db.scalars(select(BorrowMethod).order_by(BorrowMethod.sort_order)).all()
    return templates.TemplateResponse(request, "spaces/admin_room_form.html", {
        "room": room, "facilities": facilities, "is_new": is_new, "errors": errors or [],
        "methods": methods, "buildings": BUILDINGS,
    }, status_code=status)


@router.get("/admin/rooms/new", include_in_schema=False)
def admin_room_new(request: Request, db: Db, _admin: AdminPage):
    return _form_page(request, db, {"building": PLAN_BUILDING, "category": "classroom", "bookable": True}, "", True)


@router.get("/admin/rooms/{room_id}/edit", include_in_schema=False)
def admin_room_edit(request: Request, db: Db, _admin: AdminPage, room_id: int):
    room = _get_room(db, room_id, include_inactive=True)
    data = {c.key: getattr(room, c.key) for c in Room.__table__.columns}
    return _form_page(request, db, data, facilities_text(room.facilities), False)


@router.post("/admin/rooms/new", include_in_schema=False)
def admin_room_create(request: Request, db: Db, _admin: AdminPage, form: RoomForm, panorama: PanoramaFile = None):
    return _save_room(request, db, form, panorama, None)


@router.post("/admin/rooms/{room_id}/edit", include_in_schema=False)
def admin_room_update(request: Request, db: Db, _admin: AdminPage, room_id: int, form: RoomForm,
                      panorama: PanoramaFile = None):
    return _save_room(request, db, form, panorama, room_id)


def _save_room(request, db, form: dict, panorama, room_id: int | None):
    verify_csrf(request, form["csrf_token"])
    room = _get_room(db, room_id, include_inactive=True) if room_id is not None else None
    clean = {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()}
    errors = []
    data = {
        "code": clean["code"].replace(" ", ""),
        "alias": clean["alias"] or None,
        "building": clean["building"] if clean["building"] in BUILDINGS else PLAN_BUILDING,
        "room_type": clean["room_type"] or None,
        "category": clean["category"] if clean["category"] in CATEGORIES else "other",
        "bookable": clean["bookable"] == "1",
        "manager": clean["manager"] or None,
        "borrow_method": clean["borrow_method"] or None,
        "location": clean["location"] or None,
        "description": clean["description"],
        "usage_note": clean["usage_note"] or None,
        "note": clean["note"] or None,
    }
    data["name"] = clean["name"] or data["alias"] or data["room_type"] or data["code"]
    if not data["code"]:
        errors.append("請填寫教室編號。")
    elif db.scalar(select(Room.id).where(Room.code == data["code"], Room.id != (room_id or 0))):
        errors.append(f"教室編號「{data['code']}」已存在。")
    try:
        data["floor"] = parse_floor(clean["floor"])
    except ValueError as e:
        errors.append(str(e))
        data["floor"] = None
    if clean["capacity"].isdigit() and int(clean["capacity"]) > 0:
        data["capacity"] = int(clean["capacity"])
    else:
        errors.append("可容納人數必須是大於 0 的整數。")
        data["capacity"] = None
    if data["borrow_method"] and db.get(BorrowMethod, data["borrow_method"]) is None:
        data["borrow_method"] = None
    if not data["bookable"]:
        data["borrow_method"] = "not_bookable"

    pano_bytes = None
    try:
        pano_bytes = read_upload(panorama)
        if pano_bytes and not image_info(pano_bytes):
            errors.append("360° 照片只接受 JPG 或 PNG。")
    except ValueError as e:
        errors.append(str(e))

    if errors:
        current = {c.key: getattr(room, c.key) for c in Room.__table__.columns} if room else {}
        return _form_page(request, db, {**current, **data, "id": room_id}, clean["facilities"],
                          room_id is None, errors, status=400)

    moved = room is not None and (room.building, room.floor) != (data["building"], data["floor"])
    if room is None:
        room = Room(**data)
        db.add(room)
    else:
        for key, value in data.items():
            setattr(room, key, value)
        if moved:
            room.map_x = room.map_y = None      # 換樓層後原本的平面圖位置不適用
    # 先刪舊設備再新增，避免同名設備撞到 (room_id, name) 唯一約束
    room.facilities.clear()
    db.flush()
    room.facilities.extend(RoomFacility(name=n, quantity=q) for n, q in parse_facilities(clean["facilities"]))

    old_pano = room.panorama_path
    remove_old = False
    if pano_bytes:
        db.flush()
        room.panorama_path, _, _ = save_upload(pano_bytes, "panoramas", f"room{room.id}")
        remove_old = True
    elif clean["remove_panorama"] == "1" and old_pano:
        room.panorama_path = None
        remove_old = True
    plan = get_floor_plan(db, data["floor"], data["building"])
    room.floor_plan_path = plan.image_path if plan else None
    db.commit()
    if remove_old:
        delete_upload(old_pano)        # 資料庫成功後才刪舊檔
    verb = "新增" if room_id is None else "更新"
    return redirect_with_message("/admin/rooms", f"已{verb}「{room.code}」。")


@router.post("/admin/rooms/{room_id}/delete", include_in_schema=False)
def admin_room_delete(request: Request, db: Db, _admin: AdminPage, room_id: int,
                      csrf_token: Annotated[str, Form()] = ""):
    verify_csrf(request, csrf_token)
    room = _get_room(db, room_id, include_inactive=True)
    code, pano = room.code, room.panorama_path
    try:
        db.delete(room)
        db.commit()
    except IntegrityError:
        # 已有預約或排課紀錄（rooms.id 被其他模組引用）：改為停用，保留歷史紀錄
        db.rollback()
        room = db.get(Room, room_id)
        room.active = False
        db.commit()
        return redirect_with_message(
            "/admin/rooms", f"「{code}」已有預約或課程紀錄，改為停用（查詢頁不再顯示）。", "warning")
    delete_upload(pano)
    return redirect_with_message("/admin/rooms", f"已刪除「{code}」。")


@router.post("/admin/rooms/{room_id}/restore", include_in_schema=False)
def admin_room_restore(request: Request, db: Db, _admin: AdminPage, room_id: int,
                       csrf_token: Annotated[str, Form()] = ""):
    verify_csrf(request, csrf_token)
    room = _get_room(db, room_id, include_inactive=True)
    room.active = True
    db.commit()
    return redirect_with_message("/admin/rooms", f"已恢復「{room.code}」。")


# ================================================================ 管理員：樓層平面圖與教室標記
@router.get("/admin/floorplans", include_in_schema=False)
def admin_floorplans(request: Request, db: Db, _admin: AdminPage, floor: str = "", room: str = ""):
    floors = all_floors(db, PLAN_BUILDING)
    current = _int_or_none(floor)
    if current not in floors:
        current = floors[0] if floors else 1
    rooms = rooms_on_floor(db, current)
    plan_row = get_floor_plan(db, current)
    return templates.TemplateResponse(request, "spaces/admin_floorplans.html", {
        "floors": floors, "current": current, "rooms": rooms, "has_image": plan_row is not None,
        "plan": build_plan(rooms, plan_row), "selected": room,
    })


@router.post("/admin/floorplans/upload", include_in_schema=False)
def admin_floorplan_upload(request: Request, db: Db, _admin: AdminPage,
                           floor: Annotated[int, Form()], image: Annotated[UploadFile | None, File()] = None,
                           csrf_token: Annotated[str, Form()] = ""):
    verify_csrf(request, csrf_token)
    back = f"/admin/floorplans?floor={floor}"
    try:
        data = read_upload(image)
    except ValueError as e:
        return redirect_with_message(back, str(e), "warning")
    if not data or not image_info(data):
        return redirect_with_message(back, "請選擇 JPG 或 PNG 平面圖。", "warning")
    path, w, h = save_upload(data, "floorplans", f"floor{floor}")
    plan = get_floor_plan(db, floor)
    old = plan.image_path if plan else None
    if plan:
        plan.image_path, plan.width, plan.height = path, w, h
    else:
        db.add(FloorPlan(building=PLAN_BUILDING, floor=floor, image_path=path, width=w, height=h))
    db.flush()
    sync_floor_plan_paths(db, floor)
    db.commit()
    delete_upload(old)
    return redirect_with_message(back, "平面圖已更新，請在圖上確認各教室位置。")


@router.post("/admin/floorplans/remove", include_in_schema=False)
def admin_floorplan_remove(request: Request, db: Db, _admin: AdminPage, floor: Annotated[int, Form()],
                           csrf_token: Annotated[str, Form()] = ""):
    verify_csrf(request, csrf_token)
    plan = get_floor_plan(db, floor)
    old = plan.image_path if plan else None
    if plan:
        db.delete(plan)
        for room in db.scalars(select(Room).where(Room.building == PLAN_BUILDING, Room.floor == floor)):
            room.map_x = room.map_y = None      # 位置是對應舊圖的，改回自動示意圖
        db.flush()
        sync_floor_plan_paths(db, floor)
        db.commit()
        delete_upload(old)
    return redirect_with_message(f"/admin/floorplans?floor={floor}", "已移除平面圖，改顯示自動示意圖。")


@router.post("/admin/floorplans/position", include_in_schema=False)
def admin_floorplan_position(request: Request, db: Db, _admin: AdminPage, floor: Annotated[int, Form()],
                             room_id: Annotated[int, Form()], x: Annotated[float, Form()],
                             y: Annotated[float, Form()], csrf_token: Annotated[str, Form()] = ""):
    verify_csrf(request, csrf_token)
    back = f"/admin/floorplans?floor={floor}"
    room = db.get(Room, room_id)
    if room is None or room.building != PLAN_BUILDING or room.floor != floor:
        return redirect_with_message(back, "找不到該樓層的教室。", "warning")
    room.map_x = round(min(max(x, 0.0), 100.0), 2)
    room.map_y = round(min(max(y, 0.0), 100.0), 2)
    db.commit()
    return redirect_with_message(f"{back}&room={room_id}", f"已更新 {room.code} 的位置。")
