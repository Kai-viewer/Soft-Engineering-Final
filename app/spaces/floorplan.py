"""平面圖與大樓地圖：計算 SVG 上每間教室「圓點」的位置與點開後的資訊卡內容。"""
from types import SimpleNamespace

from app.spaces.models import CATEGORIES, FloorPlan, Room
from app.spaces.service import STATIC_URL, floor_label

SCHEMATIC_W, SCHEMATIC_H = 1000, 560

# ---------------------------------------------------------------- Google 地圖截圖
BUILDING_MAP = {
    "image": STATIC_URL + "building_map.png",
    "width": 620, "height": 388,
    "google_url": "https://www.google.com/maps/place/%E5%9C%8B%E7%AB%8B%E6%9A%A8%E5%8D%97%E5%9C%8B%E9%9A%9B%E5%A4%A7%E5%AD%B8%E7%AE%A1%E7%90%86%E5%AD%B8%E9%99%A2/@23.9523128,120.9272352,18z",
    "attribution": "影像 © Airbus、Maxar Technologies；地圖資料 © Google",
}

# 官方平面圖（百分比）→ Google 地圖截圖（百分比）的仿射轉換。
# 六張官方平面圖的大樓外框位置相同，所以各樓層共用一組係數。
# 由 6 個兩張圖都認得出的地標擬合（U 字形四個外角、半圓會議廳中心、北側翼轉角），
# 衛星圖相對平面圖約旋轉 3.4°，誤差約 1～1.5%，作為「大約位置」使用。
PLAN_TO_MAP = ((1.04966, -0.01915, 13.4565), (0.09935, 0.94257, -7.7047))

# 大樓出入口（以官方平面圖百分比座標記錄，畫在地圖上時同樣換算）
ENTRANCES = [
    {"title": "西側入口", "floor": 2, "plan": (7.0, 49.7), "side": "left"},
    {"title": "主要出入口", "floor": 1, "plan": (35.9, 89.0), "side": "below"},
    {"title": "東側入口", "floor": -1, "plan": (65.6, 81.8), "side": "right"},
]


def plan_to_map(x: float, y: float) -> tuple[float, float]:
    (a, b, c), (d, e, f) = PLAN_TO_MAP
    return round(a * x + b * y + c, 2), round(d * x + e * y + f, 2)


def is_official_plan(plan: FloorPlan | None) -> bool:
    return bool(plan and plan.image_path.startswith(STATIC_URL + "floorplans/"))


def schematic_positions(codes: list[str]) -> dict[str, tuple[float, float]]:
    """沒有平面圖的樓層：依房號排成「走廊上下兩排」的示意位置（0～100）"""
    codes = sorted(codes)
    per_row = max(1, (len(codes) + 1) // 2)
    return {code: (round(10 + 80 * ((i // 2 + 0.5) / per_row), 2), 30.0 if i % 2 == 0 else 72.0)
            for i, code in enumerate(codes)}


def build_plan(rooms: list[Room], plan: FloorPlan | None = None, highlight_id: int | None = None,
               positions: dict | None = None, dot_scale: float | None = None) -> dict:
    """
    rooms：該樓層教室；plan：有 width / height / image_path 的平面圖（None＝畫示意圖）
    positions：{教室編號: (x%, y%)}，不給時用 rooms.map_x / map_y
    """
    if positions is None:
        positions = {r.code: (r.map_x, r.map_y) for r in rooms if r.map_x is not None}
    if plan:
        W, H = plan.width, plan.height
    else:
        # 沒有平面圖：管理員標過的位置優先，其餘自動排成示意圖
        W, H = SCHEMATIC_W, SCHEMATIC_H
        auto = schematic_positions([r.code for r in rooms])
        positions = {**auto, **positions}
    unit = max(W, H)

    dots, info = [], {}
    for r in rooms:
        if r.code not in positions:
            continue
        x, y = positions[r.code]
        dots.append({
            "id": r.id, "code": r.code, "category": r.category,
            "cx": round(x / 100 * W, 1), "cy": round(y / 100 * H, 1),
            "highlight": r.id == highlight_id,
            "label": f"{r.code} {r.alias or ''}".strip(),
        })
        info[r.id] = {
            "id": r.id, "code": r.code, "alias": r.alias,
            "type": r.room_type or CATEGORIES.get(r.category, ""),
            "category": CATEGORIES.get(r.category, r.category), "categoryKey": r.category,
            "capacity": r.capacity, "manager": r.manager, "floor": floor_label(r.floor),
            "bookable": r.bookable, "hasPanorama": bool(r.panorama_path),
            "facilities": [f.name + (f"×{f.quantity}" if f.quantity else "") for f in r.facilities][:8],
            "url": f"/rooms/{r.id}",
        }
    return {
        "image": plan.image_path if plan else None,
        "W": W, "H": H,
        "dot_r": round(unit * (dot_scale or (0.0075 if plan else 0.014)), 1),
        "font": round(unit * 0.016, 1),
        "dots": dots,        # 不能叫 items：Jinja 的 plan.items 會變成 dict.items() 方法
        "info": info,
        "unplaced": [r for r in rooms if r.code not in positions],
    }


def build_site_map(rooms: list[Room], plan: FloorPlan | None) -> dict | None:
    """
    Google 地圖截圖上標出本層每間教室的大約位置。
    只有官方平面圖的座標能換算；管理員換過圖的樓層回傳 None。
    """
    if not is_official_plan(plan):
        return None
    positions = {r.code: plan_to_map(r.map_x, r.map_y) for r in rooms if r.map_x is not None}
    image = SimpleNamespace(width=BUILDING_MAP["width"], height=BUILDING_MAP["height"],
                            image_path=BUILDING_MAP["image"])
    site = build_plan(rooms, image, positions=positions, dot_scale=0.011)
    site["entrances"] = [
        {**e, "x": plan_to_map(*e["plan"])[0], "y": plan_to_map(*e["plan"])[1]} for e in ENTRANCES
    ]
    return site
