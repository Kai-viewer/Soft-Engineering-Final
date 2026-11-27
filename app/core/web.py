from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")
templates = Jinja2Templates(directory=APP_DIR / "templates")


def local_time(value: datetime) -> str:
    # SQLite's test driver returns naive datetimes for UTC values.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TAIPEI).strftime("%Y/%m/%d %H:%M")


templates.env.filters["local_time"] = local_time
