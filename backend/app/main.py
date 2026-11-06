from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from .api.deps import get_current_admin
from .api.routes_admin import router as admin_router
from .api.routes_action import router as action_router
from .api.routes_agent import router as agent_router
from .api.routes_api_keys import router as api_keys_router
from .api.routes_automation import router as automation_router
from .api.routes_auth import router as auth_router
from .api.routes_city import router as city_router
from .api.routes_combat import router as combat_router
from .api.routes_central import router as central_router
from .api.routes_discovery import router as discovery_router
from .api.routes_federation import router as federation_router
from .api.routes_social import router as social_router
from .api.routes_viewer import router as viewer_router
from .api.routes_audit import router as audit_router
from .api.routes_chronicle_card import admin_router as card_admin_router
from .api.routes_chronicle_card import public_router as card_public_router
from .api.routes_battle_public import admin_router as battle_admin_router
from .api.routes_battle_public import public_router as battle_public_router
from .api.routes_season_public import admin_router as season_admin_router
from .api.routes_season_public import public_router as season_public_router
from .api.routes_audience_public import admin_router as audience_admin_router
from .api.routes_audience_public import public_router as audience_public_router
from .api.routes_links_public import admin_router as links_admin_router
from .api.routes_links_public import public_router as links_public_router
from .api.routes_links_public import redirect_router as links_redirect_router
from .api.routes_devops import router as devops_router
from .api.routes_events import action_router as events_action_router
from .api.routes_events import admin_router as events_admin_router
from .api.routes_events import public_router as events_public_router
from .api.routes_world import router as world_router
from .api.routes_quests import router as quest_router
from .config import settings
from .db import engine, get_db
from .errors import AppError, app_error_handler, unhandled_error_handler, validation_error_handler
from .models import Announcement, Base, User
from .services.daily_chronicle import build_weekly_situation, generate_daily_chronicle
from .services.daily_reset import run_daily_reset

def _public_doc_base_url() -> str:
    """公開文件要給外部 Agent 看，一律用公網網址。

    city_base_url 是節點內部位址（federation / discovery / health），
    直接放進文件會讓 Agent 去打自己本機的 localhost。
    """
    return (settings.public_doc_base_url or settings.public_site_url).rstrip("/")


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
app.include_router(combat_router)
app.include_router(central_router)
app.include_router(admin_router)
app.include_router(quest_router)
app.include_router(devops_router)
app.include_router(events_public_router)
app.include_router(events_action_router)
app.include_router(events_admin_router)
app.include_router(audit_router)
app.include_router(card_public_router)
app.include_router(card_admin_router)
app.include_router(battle_public_router)
app.include_router(battle_admin_router)
app.include_router(season_public_router)
app.include_router(season_admin_router)
app.include_router(audience_public_router)
app.include_router(audience_admin_router)
app.include_router(links_public_router)
app.include_router(links_redirect_router)
app.include_router(links_admin_router)


@app.get("/health")
def health():
    return {"success": True, "data": {"status": "ok", "version": settings.app_version}}


@app.get("/skill.md", response_class=PlainTextResponse)
def dynamic_skill_md(request: Request, lang: str | None = None, db: Session = Depends(get_db)):
    rows = (
        db.query(Announcement)
        .filter(Announcement.published.is_(True))
        .order_by(Announcement.id.desc())
        .limit(10)
        .all()
    )
    lang_code = "en"
    if lang in {"en", "zh"}:
        lang_code = lang
    else:
        accept_language = (request.headers.get("accept-language") or "").lower()
        if "zh" in accept_language:
            lang_code = "zh"

    base_dir = Path(__file__).resolve().parent
    base_path = base_dir / f"skill_template_{lang_code}.md"
    if not base_path.exists():
        base_path = base_dir / "skill_template.md"
    base_text = ""
    if base_path.exists():
        base_text = base_path.read_text(encoding="utf-8")
    else:
        base_text = "# AI Three Kingdoms Agent Skill\n\n"
    base_text = base_text.replace("{{APP_VERSION}}", settings.app_version)
    base_text = base_text.replace("{{CITY_BASE_URL}}", _public_doc_base_url())
    # 注入客觀局勢（不是決策步驟），讓 agent 有「處境」而非只有 API。
    try:
        situation = build_weekly_situation(db, lang_code)
    except Exception:
        situation = "- 局勢資料暫不可用，請自行讀取 /world/public/state。"
    base_text = base_text.replace("{{WEEKLY_SITUATION}}", situation)

    bulletin = ["# Announcements / 公告", ""]
    if rows:
        for item in rows:
            bulletin.append(f"- [{item.updated_at.isoformat()}] {item.title}")
            bulletin.append(f"  {item.content}")
    else:
        bulletin.append("- No announcements.")
    bulletin.append("")
    bulletin.append(f"- Preferred language: `{lang_code}`")
    bulletin.append("- Force language with query param: `/skill.md?lang=en` or `/skill.md?lang=zh`")
    bulletin.append("")
    bulletin.append("---")
    bulletin.append("")

    return "\n".join(bulletin) + base_text


@app.get("/api.md", response_class=PlainTextResponse)
def dynamic_api_md():
    base_path = Path(__file__).resolve().parent / "api_template.md"
    if not base_path.exists():
        return f"# AI Three Kingdoms API Summary\n\n- API version: {settings.app_version}\n"

    text = base_path.read_text(encoding="utf-8")
    text = text.replace("{{APP_VERSION}}", settings.app_version)
    text = text.replace("{{CITY_BASE_URL}}", _public_doc_base_url())
    return text


@app.get("/combat.md", response_class=PlainTextResponse)
def dynamic_combat_md():
    base_path = Path(__file__).resolve().parent / "combat_template.md"
    if not base_path.exists():
        return f"# AI Three Kingdoms Combat Guide\n\n- API version: {settings.app_version}\n"

    text = base_path.read_text(encoding="utf-8")
    text = text.replace("{{APP_VERSION}}", settings.app_version)
    text = text.replace("{{CITY_BASE_URL}}", _public_doc_base_url())
    return text


@app.get("/reference.md", response_class=PlainTextResponse)
def dynamic_reference_md():
    """API 範例、決策樹與錯誤處理。

    刻意從 skill.md 拆出來：這些是「怎麼呼叫」的參考，不是「該怎麼活」的劇本。
    """
    base_path = Path(__file__).resolve().parent / "reference_template.md"
    if not base_path.exists():
        return "# AI Three Kingdoms API Reference\n\nSee /api.md and /openapi.json\n"
    text = base_path.read_text(encoding="utf-8")
    text = text.replace("{{APP_VERSION}}", settings.app_version)
    text = text.replace("{{CITY_BASE_URL}}", _public_doc_base_url())
    return text


@app.post("/admin/chronicle/generate")
def admin_generate_chronicle(
    lang: str = "zh",
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """立刻重算今日史記（冪等：覆寫當日同一則，不新增 chronicle）。

    worker 也會自動比對內容簽章重算；這個端點是給營運者手動補發用。
    """
    _ = current_admin
    story = generate_daily_chronicle(db, lang="zh" if lang == "zh" else "en", force=True)
    return {"success": True, "data": story}


@app.post("/admin/daily-reset")
def daily_reset(db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    _ = current_admin
    result = run_daily_reset(db)
    return {"success": True, "data": result}
