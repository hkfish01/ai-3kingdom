from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from .api.deps import get_current_admin
from .api.routes_admin import router as admin_router
from .api.routes_action import router as action_router
from .api.routes_agent import router as agent_router
from .api.routes_api_keys import router as api_keys_router
from .api.routes_automation import router as automation_router
from .api.routes_auth import router as auth_router
from .api.routes_city import router as city_router
from .api.routes_discovery import router as discovery_router
from .api.routes_federation import router as federation_router
from .api.routes_social import router as social_router
from .api.routes_viewer import router as viewer_router
from .api.routes_world import router as world_router
from .config import settings
from .db import engine, get_db
from .errors import AppError, app_error_handler, unhandled_error_handler, validation_error_handler
from .models import Base, User
from .services.daily_reset import run_daily_reset

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

if settings.auto_create_schema:
    Base.metadata.create_all(bind=engine)

app.include_router(auth_router)
app.include_router(agent_router)
app.include_router(api_keys_router)
app.include_router(automation_router)
app.include_router(viewer_router)
app.include_router(world_router)
app.include_router(action_router)
app.include_router(social_router)
app.include_router(federation_router)
app.include_router(discovery_router)
app.include_router(city_router)
app.include_router(admin_router)


@app.get("/health")
def health():
    return {"success": True, "data": {"status": "ok", "version": settings.app_version}}


@app.post("/admin/daily-reset")
def daily_reset(db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    _ = current_admin
    result = run_daily_reset(db)
    return {"success": True, "data": result}
