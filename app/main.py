from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.accounts import router as accounts
from app.bookings import router as bookings
from app.core.db import make_engine
from app.core.web import APP_DIR, templates
from app.scheduling import router as scheduling
from app.spaces import router as spaces
from app.accounts.router import OptionalUser


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.engine = make_engine()
        try:
            yield
        finally:
            application.state.engine.dispose()

    application = FastAPI(title="管院空間管理", lifespan=lifespan)
    application.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    for module in (accounts, spaces, bookings, scheduling):
        application.include_router(module.router)

    @application.get("/", include_in_schema=False)
    def home(request: Request, _user: OptionalUser):
        return templates.TemplateResponse(request, "home.html")

    return application


app = create_app()
