"""
暨大國企系網站「教室空間」爬蟲（管理學院空間資料）
來源：https://www.ibs.ncnu.edu.tw/index.php/resources/space-classroom

只用 Python 標準函式庫，不需安裝套件：
    uv run python app/spaces/tools/scrape_spaces.py
輸出（寫到 app/spaces/data/，由 app/spaces/seed.py 匯入資料庫）：
    spaces.json         完整結構化資料（空間 + 借用規則 + 資料問題）
    spaces.csv          一列一空間，Excel 可直接開
    booking_rules.json  借用流程（從「管院教室借用方法」文章整理）
    spaces.sql          PostgreSQL 建表 + 匯入資料
"""
import csv
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://www.ibs.ncnu.edu.tw"
LIST_URL = BASE + "/index.php/resources/space-classroom"
PAGE_SIZE = 18  # 網站每頁 18 筆（?start=0, 18, 36 ...）
OUT_DIR = Path(__file__).resolve().parent.parent / "data"   # app/spaces/data
UA = {"User-Agent": "Mozilla/5.0 (course project scraper)"}
GUIDE_TITLE_KEYWORD = "借用方法"

# 詳細頁欄位（中文標籤 -> 英文欄位名）
FIELD_MAP = {
    "空間": "space_name",
    "可容納人數": "capacity_text",
    "管理單位": "manager_raw",
    "所在位置": "location",
    "設備與配備": "equipment_text",
    "設備": "equipment_text",
    "使用方式": "usage",
    "備註": "note",
    "人員": "staff",
}

MANAGER_ALIAS = {
    "管院辦公室": "管理學院辦公室",
    "逕洽管院祕書": "管理學院祕書",
    "國比系": "國比系辦公室",
}

# 借用方式代碼（依「管院教室借用方法」文章）
BOOKING_METHODS = {
    "ibs_system": {
        "manager_unit": "國企系",
        "description": "使用國企系借教室系統線上預約",
        "url": BASE + "/index.php/resources/classroom-booking",
    },
    "college_form": {
        "manager_unit": "管理學院",
        "description": "至管理學院辦公室洽詢工讀生預約 → 填寫「管理學院場所借用申請單」交系辦 → 系主任簽章核可後交回管理學院辦公室",
        "url": "https://cm.ncnu.edu.tw/var/file/66/1066/img/507/309219402.doc",
    },
    "contact_secretary": {
        "manager_unit": "管理學院祕書",
        "description": "逕洽管院祕書",
        "url": None,
    },
    "contact_department": {
        "manager_unit": "管院外系",
        "description": "請至該系系辦公室詢問",
        "url": None,
    },
    "not_bookable": {
        "manager_unit": None,
        "description": "辦公室／研究室，非公開借用空間",
        "url": None,
    },
    "unknown": {
        "manager_unit": None,
        "description": "網站未註明管理單位，需另行確認",
        "url": None,
    },
}

# room_type 關鍵字 -> (category, bookable)；依序比對，先中先贏
CATEGORY_RULES = [
    ("主任辦公室", "office", False),
    ("辦公室", "office", False),
    ("研究室", "research_room", False),
    ("會議廳", "hall", True),
    ("會議室", "meeting_room", True),
    ("研討室", "seminar_room", True),
    ("咖啡", "lounge", True),
    ("教室", "classroom", True),
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def strip_tags(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|div|li|h\d|tr)>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).replace("\xa0", " ")


def article_body(page: str) -> str:
    m = re.search(r'<div itemprop="articleBody">(.*?)<div class="attachmentsContainer">', page, flags=re.S)
    return m.group(1) if m else ""


def list_articles() -> list[dict]:
    """逐頁抓列表，回傳 [{article_id, title, url}]，直到某頁沒有新文章為止。"""
    seen, items, start = set(), [], 0
    while True:
        page = fetch(f"{LIST_URL}?start={start}")
        links = re.findall(
            r'<h2[^>]*>\s*<a href="(/index\.php/resources/space-classroom/(\d+)-[^"]*)"[^>]*>\s*(.*?)\s*</a>',
            page, flags=re.S)
        new = [(u, i, t) for u, i, t in links if i not in seen]
        if not new:
            break
        for u, i, t in new:
            seen.add(i)
            items.append({"article_id": int(i), "title": html.unescape(t).strip(),
                          "url": BASE + u, "list_page_start": start})
        start += PAGE_SIZE
        time.sleep(0.5)
    return items


# ---------------------------------------------------------------- 解析詳細頁
def parse_detail(page: str, title: str) -> dict:
    body = article_body(page)
    lines = [l.strip() for l in strip_tags(body).splitlines() if l.strip()]
    info, unlabeled = {}, []
    for line in lines:
        mm = re.match(r"^([^：:]{1,8})[：:]\s*(.*)$", line)
        key = mm.group(1).strip() if mm else None
        if key in FIELD_MAP and FIELD_MAP[key] not in info:
            info[FIELD_MAP[key]] = mm.group(2).strip()
        elif line.replace(" ", "") != title.replace(" ", "") and not re.match(r"^.+/.+/", line):
            unlabeled.append(line)
    # 教A 系列教室的設備沒有標籤，只是一行「投影機、DVD播放機、數位講桌」
    if "equipment_text" not in info:
        eq = [l for l in unlabeled if "、" in l and len(l) < 60]
        if eq:
            info["equipment_text"] = eq[0]
            unlabeled.remove(eq[0])
    if unlabeled:
        info["description"] = "\n".join(unlabeled)
    imgs = re.findall(r'<img[^>]+(?:data-src|src)="([^"]+)"', body)
    info["images"] = [i if i.startswith("http") else BASE + "/" + i.lstrip("/") for i in imgs]
    info["raw_text"] = "\n".join(lines)
    return info


def parse_guide(page: str) -> dict:
    """解析「管院教室借用方法」：借用步驟文字 + 管院教室列表表格。"""
    body = article_body(page)
    table_html = body[body.find("<table"):] if "<table" in body else ""
    before = body[:body.find("<table")] if table_html else body
    steps = [l.strip() for l in strip_tags(before).splitlines() if l.strip() and l.strip() != "管院教室列表"]
    links = [{"text": html.unescape(re.sub(r"<[^>]+>", "", t)).strip(),
              "url": u if u.startswith("http") else BASE + u}
             for u, t in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', before, flags=re.S)]
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", table_html, flags=re.S):
        cells = [re.sub(r"\s*\n\s*", "", strip_tags(td)).strip()
                 for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        if len(cells) < 3 or cells[0] == "管理單位":
            continue
        name = cells[1]
        m = re.match(r"^(管\s*B?\d+)(.*)$", name)
        code = m.group(1).replace(" ", "") if m else name
        alias = m.group(2).strip() if m else ""
        cap = re.search(r"\d+", cells[2])
        rows.append({
            "manager_unit": cells[0],
            "room_code": code,
            "name_in_table": name,
            "alias": alias if alias.endswith("廳") else None,  # 巴菲特廳、賈伯斯廳…
            "capacity": int(cap.group()) if cap else None,
            "equipment": split_equipment(cells[3] if len(cells) > 3 else ""),
        })
    return {"steps": steps, "links": links, "room_table": rows}


# ---------------------------------------------------------------- 正規化
def parse_title(title: str) -> dict:
    """'管320/經濟系研討室/15人' -> room_code, building, room_no, floor, room_type, capacity"""
    parts = [p.strip() for p in title.split("/")]
    code = parts[0].replace(" ", "") if parts else title
    building = {"管": "管理學院", "教": "教育學院"}.get(code[:1])
    no = code[1:]
    if "~" in no:                      # 管5003~5119 教師研究室（範圍）
        floor = int(no[0])
    elif no.upper().startswith("B"):   # 地下室 B11/B15/B24 -> -1
        floor = -1
    else:
        digits = re.sub(r"\D", "", no)
        floor = int(digits[0]) if digits else None
    cap = None
    if len(parts) > 2:
        mc = re.search(r"(\d+)\s*人", parts[2])
        cap = int(mc.group(1)) if mc else None
    return {"room_code": code, "building": building, "room_no": no, "floor": floor,
            "room_type": parts[1] if len(parts) > 1 else None, "capacity": cap}


def split_equipment(s: str | None) -> list[dict]:
    """'鐵櫃*2、無線麥克風1支、投影機' -> [{name, qty}]"""
    out = []
    for item in re.split(r"[、,，;；]", s or ""):
        item = item.strip()
        if not item:
            continue
        m = re.match(r"^(.*?)\s*[\*＊]\s*(\d+)$", item) or re.match(r"^(.*?\D)(\d+)\s*[個支座台張]$", item)
        out.append({"name": m.group(1).strip(), "qty": int(m.group(2))} if m else {"name": item, "qty": None})
    return out


def classify(room_type: str | None) -> tuple[str, bool]:
    for kw, cat, bookable in CATEGORY_RULES:
        if room_type and kw in room_type:
            return cat, bookable
    return "other", False


def booking_method(manager: str | None, bookable: bool) -> str:
    if not bookable:
        return "not_bookable"
    if not manager:
        return "unknown"
    if manager.startswith("國企系"):
        return "ibs_system"
    if manager == "管理學院辦公室":
        return "college_form"
    if manager == "管理學院祕書":
        return "contact_secretary"
    return "contact_department"


def to_int(s):
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else None


def build_room(article: dict, detail: dict, guide_rows: dict, issues: list) -> dict:
    t = parse_title(article["title"])
    # 「所在位置」比房號可靠（例：教A000 在 B1 樓）
    loc = detail.get("location") or ""
    mf = re.search(r"(B|地下)\s*(\d)\s*樓", loc) or re.search(r"(\d+)\s*樓", loc)
    if mf:
        t["floor"] = -int(mf.group(2)) if mf.lastindex == 2 else int(mf.group(1))
    cat, bookable = classify(t["room_type"])
    g = guide_rows.get(t["room_code"])

    manager = detail.get("manager_raw")
    manager = MANAGER_ALIAS.get(manager, manager)
    if not manager and g:
        manager = g["manager_unit"] + ("辦公室" if g["manager_unit"].endswith("系") else "辦公室")
        issues.append(f"{t['room_code']}：詳細頁沒寫管理單位，改用借用方法表格的「{g['manager_unit']}」")

    capacity = t["capacity"] or to_int(detail.get("capacity_text"))
    if g and g["capacity"] and capacity and g["capacity"] != capacity:
        issues.append(f"{t['room_code']}：人數不一致（空間頁 {capacity} 人 / 借用方法表格 {g['capacity']} 人），採用空間頁")

    equipment = split_equipment(detail.get("equipment_text"))
    if not equipment and g and g["equipment"]:
        equipment = g["equipment"]

    return {
        "article_id": article["article_id"],
        "room_code": t["room_code"],
        "building": t["building"],
        "room_no": t["room_no"],
        "floor": t["floor"],
        "room_type": t["room_type"],
        "alias": g["alias"] if g else None,
        "category": cat,
        "bookable": bookable,
        "capacity": capacity,
        "manager": manager,
        "booking_method": booking_method(manager, bookable),
        "location": detail.get("location"),
        "equipment": equipment,
        "usage": detail.get("usage"),
        "note": detail.get("note") or detail.get("staff") and f"人員：{detail['staff']}",
        "description": detail.get("description"),
        "images": detail.get("images", []),
        "source_title": article["title"],
        "source_url": article["url"],
    }


# ---------------------------------------------------------------- 輸出
def sql_val(v) -> str:
    if v is None or v == "":
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def write_sql(rooms: list[dict], path: Path):
    L = [
        "-- 管理學院空間資料（由 scraper/scrape_spaces.py 自動產生，PostgreSQL）",
        "-- 來源：" + LIST_URL,
        "DROP TABLE IF EXISTS space_equipment;",
        "DROP TABLE IF EXISTS spaces;",
        "DROP TABLE IF EXISTS booking_methods;",
        "",
        "CREATE TABLE booking_methods (",
        "    code          VARCHAR(30) PRIMARY KEY,",
        "    manager_unit  VARCHAR(50),",
        "    description   TEXT NOT NULL,",
        "    url           TEXT",
        ");",
        "",
        "CREATE TABLE spaces (",
        "    space_id        SERIAL PRIMARY KEY,",
        "    room_code       VARCHAR(20) NOT NULL UNIQUE,   -- 管320、管B15、教A001",
        "    building        VARCHAR(20),                   -- 管理學院 / 教育學院",
        "    room_no         VARCHAR(20),",
        "    floor           SMALLINT,                      -- 地下室 = -1",
        "    room_type       VARCHAR(50),                   -- 網站原始分類，如「個案階梯教室」",
        "    alias           VARCHAR(50),                   -- 巴菲特廳、史密斯廳…",
        "    category        VARCHAR(20) NOT NULL,          -- classroom/meeting_room/seminar_room/hall/lounge/office/research_room",
        "    bookable        BOOLEAN NOT NULL DEFAULT TRUE,",
        "    capacity        INTEGER,",
        "    manager         VARCHAR(50),                   -- 管理單位",
        "    booking_method  VARCHAR(30) REFERENCES booking_methods(code),",
        "    location        VARCHAR(100),",
        "    usage_note      TEXT,",
        "    note            TEXT,",
        "    source_url      TEXT",
        ");",
        "",
        "CREATE TABLE space_equipment (",
        "    space_id   INTEGER NOT NULL REFERENCES spaces(space_id) ON DELETE CASCADE,",
        "    equipment  VARCHAR(100) NOT NULL,",
        "    quantity   INTEGER,",
        "    PRIMARY KEY (space_id, equipment)",
        ");",
        "",
        "CREATE INDEX idx_spaces_capacity ON spaces(capacity);",
        "CREATE INDEX idx_spaces_floor ON spaces(building, floor);",
        "",
    ]
    for code, b in BOOKING_METHODS.items():
        L.append(f"INSERT INTO booking_methods VALUES ({sql_val(code)}, {sql_val(b['manager_unit'])}, "
                 f"{sql_val(b['description'])}, {sql_val(b['url'])});")
    L.append("")
    cols = ["room_code", "building", "room_no", "floor", "room_type", "alias", "category", "bookable",
            "capacity", "manager", "booking_method", "location", "usage", "note", "source_url"]
    for r in rooms:
        L.append("INSERT INTO spaces (" + ", ".join(c if c != "usage" else "usage_note" for c in cols)
                 + ") VALUES (" + ", ".join(sql_val(r[c]) for c in cols) + ");")
    L.append("")
    for r in rooms:
        seen = set()
        for e in r["equipment"]:
            if e["name"] in seen:
                continue
            seen.add(e["name"])
            L.append(f"INSERT INTO space_equipment (space_id, equipment, quantity) "
                     f"SELECT space_id, {sql_val(e['name'])}, {sql_val(e['qty'])} "
                     f"FROM spaces WHERE room_code = {sql_val(r['room_code'])};")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    articles = list_articles()
    print(f"列表共 {len(articles)} 篇")

    pages = {}
    for a in articles:
        pages[a["article_id"]] = fetch(a["url"])
        time.sleep(0.5)

    guide_article = next((a for a in articles if GUIDE_TITLE_KEYWORD in a["title"]), None)
    guide = parse_guide(pages[guide_article["article_id"]]) if guide_article else {"steps": [], "links": [], "room_table": []}
    if guide_article:
        guide["source_url"] = guide_article["url"]
    guide_rows = {r["room_code"]: r for r in guide["room_table"]}

    issues, rooms = [], []
    for a in articles:
        if a is guide_article:
            continue
        detail = parse_detail(pages[a["article_id"]], a["title"])
        rooms.append(build_room(a, detail, guide_rows, issues))

    # 只出現在借用方法表格、沒有獨立空間頁的教室（例：管B24）
    known = {r["room_code"] for r in rooms}
    for code, g in guide_rows.items():
        if code not in known:
            issues.append(f"{code}：只出現在借用方法表格，沒有獨立空間頁（已補入，source_url 指向借用方法文章）")
            t = parse_title(f"{code}/教室/{g['capacity']}人")
            manager = "管理學院辦公室" if g["manager_unit"] == "管理學院" else g["manager_unit"] + "辦公室"
            rooms.append({
                "article_id": None, **{k: t[k] for k in ("room_code", "building", "room_no", "floor")},
                "room_type": "教室", "alias": g["alias"], "category": "classroom", "bookable": True,
                "capacity": g["capacity"], "manager": manager,
                "booking_method": booking_method(manager, True), "location": None,
                "equipment": g["equipment"], "usage": None, "note": "僅見於借用方法表格",
                "description": None, "images": [], "source_title": g["name_in_table"],
                "source_url": guide.get("source_url"),
            })

    def sort_key(r):
        return (r["building"] != "管理學院", r["floor"] if r["floor"] is not None else 99, r["room_code"])
    rooms.sort(key=sort_key)
    for i, r in enumerate(rooms, 1):
        r["space_id"] = i

    for r in rooms:
        print(f"  {r['room_code']:<12} {r['category']:<13} {str(r['capacity']):>4} 人  "
              f"{r['manager'] or '-':<10} {r['booking_method']}")

    scraped_at = time.strftime("%Y-%m-%d %H:%M:%S")
    booking_rules = {"source": guide.get("source_url"), "scraped_at": scraped_at,
                     "steps": guide["steps"], "links": guide["links"],
                     "methods": BOOKING_METHODS, "room_table": guide["room_table"]}
    (OUT_DIR / "booking_rules.json").write_text(json.dumps(booking_rules, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT_DIR / "spaces.json").write_text(json.dumps({
        "source": LIST_URL, "scraped_at": scraped_at, "count": len(rooms),
        "bookable_count": sum(r["bookable"] for r in rooms),
        "data_issues": issues, "spaces": rooms,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    cols = ["space_id", "room_code", "building", "floor", "room_type", "alias", "category", "bookable",
            "capacity", "manager", "booking_method", "location", "equipment", "usage", "note", "source_url"]
    with open(OUT_DIR / "spaces.csv", "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig：Excel 開不亂碼
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rooms:
            eq = "、".join(e["name"] + (f"×{e['qty']}" if e["qty"] else "") for e in r["equipment"])
            w.writerow({**r, "equipment": eq})

    write_sql(rooms, OUT_DIR / "spaces.sql")
    print(f"\n資料問題 {len(issues)} 項：")
    for s in issues:
        print("  - " + s)
    print(f"完成：{len(rooms)} 個空間，輸出到 {OUT_DIR}")


if __name__ == "__main__":
    main()
