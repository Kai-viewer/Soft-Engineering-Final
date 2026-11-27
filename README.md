# 管院空間管理

軟體工程期末專案。三個模組各自維護 FastAPI 路由、資料模型及 Jinja2 頁面，共用登入和 PostgreSQL。

## 本機啟動

先安裝 [uv](https://docs.astral.sh/uv/getting-started/installation/) 並啟動 Docker Desktop 或 Docker Engine。第一次取得專案可執行：

```sh
git clone https://github.com/Kai-viewer/Soft-Engineering-Final.git
cd Soft-Engineering-Final
```

已下載或 clone 的組員，直接在專案根目錄執行：

```sh
test -f .env || cp .env.example .env
uv sync --locked
docker compose up -d --wait db
uv run --locked alembic upgrade head
uv run --locked python -m app.seed
uv run --locked uvicorn app.main:app --reload
```

Alembic 建立資料表。接著 seed 匯入測試帳號、教室和借用紀錄。啟動後可開啟 [網站首頁](http://127.0.0.1:8000/)、[登入頁](http://127.0.0.1:8000/login) 或 [Swagger API 文件](http://127.0.0.1:8000/docs)。

### 網站測試帳號

使用範本的 `DEMO_PASSWORD=123` 並首次匯入後，可在網站登入：

| 角色 | 帳號 | 預設密碼 |
|---|---|---|
| 一般使用者 | `member` | `123` |
| 教師 | `teacher` | `123` |
| 管理員 | `admin` | `123` |

這組帳密供本機開發使用。若要自訂密碼，可在首次匯入前修改 `.env` 的 `DEMO_PASSWORD`。再次執行 seed 會保留已存在帳號的密碼。

## 分工與開發起點

三個模組的空路由已由 `app/main.py` 掛載。各組員從自己的 `router.py` 開始實作 API 和頁面，在 `app/templates/` 新增樣板。資料表、資料模型與可選的測試資料已可共用。

| 負責人 | 起點 | 要開發的功能 |
|---|---|---|
| A | `app/spaces/router.py` | 教室查詢與詳情、管理員教室增刪改、樓層標記、360° 檢視 |
| B | `app/bookings/router.py` | 借用週曆、預約和多物品選擇、審核、領用與歸還、借用紀錄 |
| C | `app/scheduling/router.py` | 教師志願、管理員課程調整與指派、週曆拖曳和衝突清單 |

`app/accounts/` 提供測試帳號的登入、登出、角色檢查與 `GET /api/accounts/me`。註冊與帳號審核介面列為共用功能的後續工作。新增寫入路由時，使用共用的登入角色依賴、檢查紀錄歸屬，並像登出一樣驗證 session 的 CSRF token。新頁面可繼承 `app/templates/base.html`。

## 資料庫管理

- 每位組員在本機執行自己的 PostgreSQL 17 容器。三個模組使用同一個 `DATABASE_URL`，並以 `users.id` 和 `rooms.id` 作為共用外鍵。借用和排課時段採具時區的時間欄位，頁面以台北時間顯示。
- 本機資料存入 Compose 的 `postgres_data` volume。平時用 `docker compose stop db` 暫停，重啟後保留資料。教室、物品和帳號的測試資料由 `app/seed.py` 建立。
- 調整 schema 時，先更新模組的 `models.py`，再用 `uv run alembic revision --autogenerate -m "describe change"` 產生遷移。檢查產出的 upgrade/downgrade，和模型一起提交 PR。重新整理分支後用 `uv run alembic heads` 確認只有一個分支頭，再執行 `uv run alembic upgrade head`。若合併後已有兩個遷移分支頭，先用 `uv run alembic merge -m "merge schema branches" <rev1> <rev2>` 建立合併遷移，再一起測試。
- `.env` 放本機設定並由 Git 忽略。若調整 PostgreSQL port，請同步修改 `POSTGRES_PORT` 和 `DATABASE_URL`。期末整合展示時，所有路由連到同一個 Demo 資料庫。

### 用 Adminer 瀏覽資料庫

在專案根目錄執行：

```sh
docker compose up -d adminer
```

Adminer 使用 PostgreSQL 的連線帳密。開啟 [本機 Adminer](http://127.0.0.1:8080/) 後，依自己的 `.env` 填寫：

| 欄位 | 取值 | `.env.example` 預設值 |
|---|---|---|
| 系統 | 選 PostgreSQL | PostgreSQL |
| 伺服器 | Compose 資料庫服務名稱 | `db` |
| 使用者 | `POSTGRES_USER` | `se_app` |
| 密碼 | `POSTGRES_PASSWORD` | `se_local_db` |
| 資料庫 | `POSTGRES_DB` | `soft_engineering` |

登入後可點選 `rooms`、`bookings` 或 `courses`，再選取資料查看紀錄。

如果 8080 已被占用，在 `.env` 加上 `ADMINER_PORT=8081`，重新啟動 Adminer，再開啟對應的本機網址。用 `docker compose stop adminer` 可以只關閉管理介面。

## 測試

```sh
uv run pytest -q
uv run alembic check
```

預設測試使用臨時 SQLite。要驗證 PostgreSQL，請以自己 `.env` 的 `DATABASE_URL` 設定 `TEST_DATABASE_URL`。以下指令使用範本的預設連線字串。測試會在各自的暫存 schema 裡套用和回滾遷移。

```sh
TEST_DATABASE_URL='postgresql+psycopg://se_app:se_local_db@127.0.0.1:55432/soft_engineering' uv run pytest -q
```
