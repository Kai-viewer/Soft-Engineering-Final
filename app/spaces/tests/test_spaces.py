"""空間查詢模組測試：查詢、詳情、平面圖、管理員增刪改與上傳。

執行：uv run python -m pytest app/spaces/tests -q
（沿用 tests/test_starter.py 的 starter fixture：套用遷移、建立測試帳號；
  設定 TEST_DATABASE_URL 時改用 PostgreSQL）
"""
import struct
import zlib

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.spaces.service import STATIC_DIR, UPLOAD_URL
from tests.test_starter import starter  # noqa: F401  共用 fixture

PASSWORD = "local-demo-password"


@pytest.fixture(autouse=True)
def upload_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    return tmp_path / "uploads"


@pytest.fixture
def spaces(starter):  # noqa: F811
    """在 starter 的測試資料之上匯入管院教室（執行兩次，確認不會重複匯入）"""
    from app.spaces.seed import seed_spaces
    client, url = starter
    engine = create_engine(url)
    first = seed_spaces(engine)
    second = seed_spaces(engine)
    engine.dispose()
    assert first["rooms_added"] > 40 and second["rooms_added"] == 0
    return client, url


def png(width=4, height=2) -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def login(client, role):
    response = client.post("/login", data={"email": f"{role}@example.test", "password": PASSWORD},
                           follow_redirects=False)
    assert response.status_code == 303
    return client.get("/api/accounts/me").json()["csrf_token"]


def room_by_code(client, code):
    return next(r for r in client.get("/api/rooms").json() if r["code"] == code)


def test_room_data_is_seeded(spaces):
    client, _ = spaces
    rooms = client.get("/api/rooms").json()
    codes = {r["code"] for r in rooms}
    assert {"管228", "管B11", "管457", "教A000", "DEMO-301"} <= codes
    assert "管431" not in codes          # 來源網站沒寫人數（rooms.capacity 必須 > 0）
    assert len(codes) == len(rooms)


def test_visitor_can_search_without_login(spaces):
    client, _ = spaces
    page = client.get("/rooms")
    assert page.status_code == 200
    assert "賈伯斯廳" in page.text
    assert "/spaces/static/spaces.css" in page.text and 'class="spaces-nav"' in page.text
    # Google 地圖已移到樓層平面圖頁，查詢頁只留連結
    assert "building_map.png" not in page.text
    assert 'href="/rooms/floorplan#map"' in page.text

    big = client.get("/api/rooms", params={"min_cap": 200}).json()
    assert big and all(r["capacity"] >= 200 for r in big)
    assert any(r["code"] == "管228" for r in client.get("/api/rooms", params={"q": "麥克風"}).json())
    assert {r["code"] for r in client.get("/api/rooms", params={"floor": -1}).json()} >= {"管B11", "管B15", "管B24"}
    projector = client.get("/api/rooms", params={"facility": "投影機"}).json()
    assert all(any(f["name"] == "投影機" for f in r["facilities"]) for r in projector)


def test_room_detail_floor_plan_and_static_files(spaces):
    client, _ = spaces
    room = room_by_code(client, "管228")
    assert room["floor_plan_path"] == "/spaces/static/floorplans/2F.png"
    assert 0 < room["map_x"] < 100 and 0 < room["map_y"] < 100

    detail = client.get(f"/rooms/{room['id']}")
    assert detail.status_code == 200
    assert "個案階梯教室" in detail.text and "管院場所借用申請單" in detail.text
    assert "登入後預約" in detail.text and "尚未提供 360° 全景照片" in detail.text
    assert 'class="pulse"' in detail.text

    plan = client.get("/rooms/floorplan", params={"floor": 2})
    # 地圖與平面圖各一組 2F 的 15 間教室
    assert plan.text.count('class="room-dot"') == 30 and plan.text.count('class="plan-info"') == 2

    assert client.get("/spaces/static/floorplans/2F.png").headers["content-type"] == "image/png"
    assert client.get("/spaces/static/spaces.css").status_code == 200
    assert client.get("/spaces/static/../router.py").status_code == 404
    assert client.get("/spaces/static/%2e%2e/router.py").status_code == 404
    missing = client.get("/rooms/99999")
    assert missing.status_code == 404 and "找不到這間教室" in missing.text


def test_admin_pages_require_admin(spaces):
    client, _ = spaces
    anonymous = client.get("/admin/rooms", follow_redirects=False)
    assert anonymous.status_code == 303 and anonymous.headers["location"] == "/login"
    login(client, "member")
    member = client.get("/admin/floorplans", follow_redirects=False)
    assert member.status_code == 303 and member.headers["location"].startswith("/rooms?msg_type=warning")


def test_admin_creates_edits_and_deletes_a_room(spaces, upload_tmp):
    client, _ = spaces
    csrf = login(client, "admin")
    form = {"code": "TEST-101", "alias": "測試廳", "building": "管理學院", "floor": "1F", "category": "meeting_room",
            "capacity": "25", "bookable": "1", "manager": "管理學院辦公室", "borrow_method": "college_form",
            "facilities": "投影機、無線麥克風*2", "csrf_token": csrf}

    assert client.post("/admin/rooms/new", data={**form, "csrf_token": "wrong"}).status_code == 403
    assert client.post("/admin/rooms/new", data={**form, "capacity": "0"}).status_code == 400
    assert client.post("/admin/rooms/new", data={**form, "code": "管228"}).status_code == 400
    assert client.post("/admin/rooms/new", data=form, files={"panorama": ("x.png", b"not an image")}).status_code == 400

    created = client.post("/admin/rooms/new", data=form, files={"panorama": ("p.png", png())}, follow_redirects=False)
    assert created.status_code == 303
    room = room_by_code(client, "TEST-101")
    assert room["name"] == "測試廳" and room["capacity"] == 25
    assert room["facilities"] == [{"name": "投影機", "quantity": None}, {"name": "無線麥克風", "quantity": 2}]
    assert room["panorama_path"].startswith(UPLOAD_URL + "panoramas/")
    pano_file = upload_tmp / room["panorama_path"].removeprefix(UPLOAD_URL)
    assert pano_file.is_file()
    assert client.get(room["panorama_path"]).status_code == 200
    assert 'id="panorama"' in client.get(f"/rooms/{room['id']}").text

    edited = client.post(f"/admin/rooms/{room['id']}/edit",
                         data={**form, "capacity": "30", "facilities": "投影機、白板", "remove_panorama": "1"},
                         follow_redirects=False)
    assert edited.status_code == 303
    room = room_by_code(client, "TEST-101")
    assert room["capacity"] == 30 and [f["name"] for f in room["facilities"]] == ["投影機", "白板"]
    assert room["panorama_path"] is None and not pano_file.exists()

    client.post(f"/admin/rooms/{room['id']}/delete", data={"csrf_token": csrf})
    assert all(r["code"] != "TEST-101" for r in client.get("/api/rooms").json())


def test_deleting_a_booked_room_only_deactivates_it(spaces):
    client, url = spaces
    csrf = login(client, "admin")
    demo = room_by_code(client, "DEMO-301")  # starter 的 seed 已建立這間教室的預約與課程
    response = client.post(f"/admin/rooms/{demo['id']}/delete", data={"csrf_token": csrf}, follow_redirects=False)
    assert "msg_type=warning" in response.headers["location"]
    assert all(r["code"] != "DEMO-301" for r in client.get("/api/rooms").json())

    from app.spaces.models import Room
    engine = create_engine(url)
    with Session(engine) as db:
        assert db.scalar(select(Room.active).where(Room.code == "DEMO-301")) is False
    engine.dispose()

    client.post(f"/admin/rooms/{demo['id']}/restore", data={"csrf_token": csrf})
    assert any(r["code"] == "DEMO-301" for r in client.get("/api/rooms").json())


def test_admin_marks_rooms_and_replaces_floor_plans(spaces, upload_tmp):
    client, _ = spaces
    csrf = login(client, "admin")
    room = room_by_code(client, "管228")

    client.post("/admin/floorplans/position",
                data={"floor": 2, "room_id": room["id"], "x": 150, "y": 20.5, "csrf_token": csrf})
    room = room_by_code(client, "管228")
    assert (room["map_x"], room["map_y"]) == (100.0, 20.5)  # 超出範圍會被夾在 0～100

    wrong_floor = client.post("/admin/floorplans/position",
                              data={"floor": 3, "room_id": room["id"], "x": 1, "y": 1, "csrf_token": csrf},
                              follow_redirects=False)
    assert "msg_type=warning" in wrong_floor.headers["location"]

    client.post("/admin/floorplans/upload", data={"floor": 2, "csrf_token": csrf}, files={"image": ("f.png", png(8, 4))})
    room = room_by_code(client, "管228")
    assert room["floor_plan_path"].startswith(UPLOAD_URL + "floorplans/")
    assert len(list((upload_tmp / "floorplans").iterdir())) == 1

    client.post("/admin/floorplans/remove", data={"floor": 2, "csrf_token": csrf})
    room = room_by_code(client, "管228")
    assert room["floor_plan_path"] is None and room["map_x"] is None
    assert not any((upload_tmp / "floorplans").iterdir())
    client.cookies.clear()                       # 前台平面圖用訪客身分看
    fallback = client.get("/rooms/floorplan", params={"floor": 2}).text
    assert "走廊（示意圖）" in fallback
    # 沒有官方平面圖就無法換算地圖位置：只顯示衛星圖、不標圓點
    assert "site-map-static" in fallback and "plan-frame site-map" not in fallback
    assert fallback.count('class="room-dot"') == 15
    assert (STATIC_DIR / "floorplans" / "2F.png").is_file()   # 內建官方圖不會被刪


def test_map_on_floor_plan_page_follows_the_selected_floor(spaces):
    client, _ = spaces
    for floor in (-1, 1, 2, 3, 4):
        rooms = client.get("/api/rooms", params={"floor": floor, "building": "管理學院"}).json()
        page = client.get("/rooms/floorplan", params={"floor": floor}).text
        site_map = page.split('id="plan"')[0]
        assert "/spaces/static/building_map.png" in site_map
        marked = [r for r in rooms if r["map_x"] is not None]
        assert site_map.count('class="room-dot"') == len(marked)
        for room in marked:
            assert f'href="/rooms/{room["id"]}"' in site_map
        # 出入口按鈕可切換樓層，目前樓層的按鈕會標示
        for target in (-1, 1, 2):
            assert f'href="/rooms/floorplan?floor={target}#map"' in site_map
        assert ('aria-current="page"' in site_map.split('class="plan-frame site-map')[1]) == (floor in (-1, 1, 2))


def test_plan_positions_convert_to_satellite_positions():
    from app.spaces.floorplan import plan_to_map
    # 官方平面圖上的地標 → Google 地圖截圖上量到的同一地標（容許約 2.5%）
    landmarks = [((3.42, 94.2), (15.16, 80.9)), ((68.32, 94.2), (83.7, 88.9)),
                 ((68.32, 27.47), (84.35, 25.3)), ((20.53, 34.16), (32.9, 25.8))]
    for plan_xy, (map_x, map_y) in landmarks:
        x, y = plan_to_map(*plan_xy)
        assert abs(x - map_x) < 2.5 and abs(y - map_y) < 2.5, (plan_xy, x, y)


@pytest.mark.parametrize("role, landing", [("admin", "/admin/rooms"), ("teacher", "/"), ("member", "/")])
def test_login_sends_only_admins_to_the_management_page(spaces, role, landing):
    client, _ = spaces
    response = client.post("/login", data={"email": f"{role}@example.test", "password": PASSWORD},
                           follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == landing
    assert client.get(landing).status_code == 200


def test_admin_has_no_search_or_floor_plan_pages(spaces):
    client, _ = spaces
    room = room_by_code(client, "管228")
    public_links = ('href="/rooms"', 'href="/rooms/floorplan')

    visitor = client.get("/rooms")
    assert all(link in visitor.text for link in public_links)
    assert 'href="/rooms"' in client.get("/").text

    login(client, "admin")
    for url in ("/rooms", "/rooms?q=228", "/rooms/floorplan", "/rooms/floorplan?floor=3"):
        response = client.get(url, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/admin/rooms", url
    for url in ("/", "/admin/rooms", "/admin/floorplans", "/admin/rooms/new", f"/rooms/{room['id']}"):
        page = client.get(url)
        assert page.status_code == 200, url
        assert not any(link in page.text for link in public_links), url
        assert 'href="/admin/' in page.text, url


@pytest.mark.parametrize("role", ["member", "teacher"])
def test_other_accounts_keep_the_public_pages(spaces, role):
    client, _ = spaces
    login(client, role)
    assert client.get("/rooms", follow_redirects=False).status_code == 200
    assert client.get("/rooms/floorplan", follow_redirects=False).status_code == 200
    assert 'href="/rooms"' in client.get("/").text
