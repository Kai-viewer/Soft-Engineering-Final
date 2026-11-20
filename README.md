# 管院空間管理

軟體工程期末專案。三個模組各自維護 FastAPI 路由、資料模型及 Jinja2 頁面，共用登入和 PostgreSQL。

## 本機啟動

先安裝 [uv](https://docs.astral.sh/uv/getting-started/installation/) 並啟動 Docker Desktop 或 Docker Engine。在 repo 根目錄執行：

```sh
test -f .env || cp .env.example .env
uv sync --locked
docker compose up -d --wait db
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload
```

開啟 [首頁](http://127.0.0.1:8000/) 或 [Swagger API 文件](http://127.0.0.1:8000/docs)。匯入測試資料時輸入至少 12 字元的本機密碼。三個測試帳號使用該密碼：`member@example.test`、`teacher@example.test`、`admin@example.test`。再次執行 seed 會補上缺少的資料，既有帳號的密碼沿用首次設定。

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

## 測試

```sh
uv run pytest -q
uv run alembic check
```

預設測試使用臨時 SQLite。要驗證 PostgreSQL 可用本機 Compose 的連線字串執行同一套測試。測試會在各自的暫存 schema 裡套用和回滾遷移。

```sh
TEST_DATABASE_URL='postgresql+psycopg://se_app:se_local_db@127.0.0.1:55432/soft_engineering' uv run pytest -q
```
