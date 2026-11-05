"""每日 08:00 史記圖卡與發文包：渲染、公開端點、冪等排程、webhook、部署設定。"""

import io
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.deps import get_current_admin
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.services import chronicle_card, chronicle_publish
from app.services.chronicle_card import (
    HEIGHT,
    WIDTH,
    build_card_svg,
    build_post_package,
    card_caption,
    render_card_png,
)
from app.services.chronicle_publish import (
    LAST_DATE_KEY,
    current_post_package,
    publish_daily_post,
)
from app.services.daily_chronicle import build_story_from_db
from app.services.system_state import get_state

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]


def test_png_card_is_1200x630_and_svg_matches_layout():
    db = SessionLocal()
    try:
        story = build_story_from_db(db, "zh")
    finally:
        db.close()

    png = render_card_png(story)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    from PIL import Image

    assert Image.open(io.BytesIO(png)).size == (WIDTH, HEIGHT)

    svg = build_card_svg(story)
    assert 'width="1200"' in svg and 'height="630"' in svg
    assert story["headline"].replace("&", "&amp;") in svg


def test_png_card_survives_missing_cjk_font(monkeypatch):
    """CI runner 沒裝 Noto CJK 時仍要能回 PNG，不能讓公開圖卡 500。"""
    monkeypatch.setattr(chronicle_card, "FONT_CANDIDATES", ())
    chronicle_card._font.cache_clear()
    try:
        db = SessionLocal()
        try:
            story = build_story_from_db(db, "zh")
        finally:
            db.close()
        assert render_card_png(story).startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        chronicle_card._font.cache_clear()


def test_post_caption_is_platform_ready_and_leaks_no_secrets():
    db = SessionLocal()
    try:
        story = build_story_from_db(db, "zh")
    finally:
        db.close()

    package = build_post_package(story)
    caption = package["caption"]
    assert story["headline"] in caption
    assert "史官曰：" in caption
    assert settings.public_site_url in caption
    assert "#AI三國" in caption
    assert "/chronicle" in package["link"]
    assert "card.png" in package["image_url"]
    assert package["date"] == story["date"]
    assert "sk-" not in caption and "claim code" not in caption.lower()
    assert card_caption(story, "zh") == caption


def test_public_card_and_post_require_no_token():
    png = client.get("/world/public/chronicle/card.png?date=2026-11-05")
    assert png.status_code == 200
    assert png.headers["content-type"].startswith("image/png")
    assert png.content.startswith(b"\x89PNG\r\n\x1a\n")

    svg = client.get("/world/public/chronicle/card.svg?lang=en")
    assert svg.status_code == 200
    assert "image/svg+xml" in svg.headers["content-type"]

    post = client.get("/world/public/chronicle/post?lang=zh")
    assert post.status_code == 200
    data = post.json()["data"]
    assert data["caption"] and data["caption_long"] and data["image_url"] and data["link"]


def test_admin_card_endpoints_stay_protected():
    assert client.post("/admin/chronicle/card/publish").status_code in (401, 403)
    assert client.get("/admin/chronicle/card/status").status_code in (401, 403)


def test_publish_is_idempotent_without_any_credentials():
    db = SessionLocal()
    try:
        first = publish_daily_post(db, force=True)
        assert first["status"] == "prepared"
        assert first["channel"] == "manual"
        assert first["package"]["caption"]
        assert get_state(db, LAST_DATE_KEY, default="") == first["date"]

        second = publish_daily_post(db)
        assert second["status"] == "skipped"
        assert second["reason"] == "already_published"

        status = chronicle_publish.publish_status(db)
        assert status["enabled"] is True
        assert status["webhook_configured"] is False
        assert status["last_result"]["status"] == "prepared"
        assert current_post_package(db)["date"] == first["date"]
    finally:
        db.close()


def test_webhook_post_sends_the_package(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    def fake_post(url, json=None, timeout=None, **kwargs):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(settings, "chronicle_card_webhook_urls", "https://hooks.test/a, https://hooks.test/b")
    monkeypatch.setattr(settings, "chronicle_card_webhook_type", "generic")
    monkeypatch.setattr(chronicle_publish.httpx, "post", fake_post)

    db = SessionLocal()
    try:
        result = publish_daily_post(db, force=True)
        assert result["status"] == "sent"
        assert len(calls) == 2
        assert calls[0]["json"]["type"] == "chronicle_card"
        assert calls[0]["json"]["image_url"].startswith("https://")
        assert calls[0]["json"]["text"] == result["package"]["caption"]
    finally:
        db.close()


def test_webhook_failure_retries_instead_of_marking_the_day_done(monkeypatch):
    def failing_post(url, json=None, timeout=None, **kwargs):
        raise RuntimeError("webhook down")

    monkeypatch.setattr(settings, "chronicle_card_webhook_urls", "https://hooks.test/a")
    monkeypatch.setattr(chronicle_publish.httpx, "post", failing_post)

    db = SessionLocal()
    try:
        result = publish_daily_post(db, force=True)
        assert result["status"] == "retrying"
        assert result["attempts"] == 1
        assert get_state(db, LAST_DATE_KEY, default="") == ""
        assert result["deliveries"][0]["ok"] is False
    finally:
        db.close()


def test_admin_manual_publish_endpoint():
    app.dependency_overrides[get_current_admin] = lambda: None
    try:
        resp = client.post("/admin/chronicle/card/publish?force=true")
        assert resp.status_code == 200
        assert resp.json()["data"]["package"]["image_url"]
        status = client.get("/admin/chronicle/card/status")
        assert status.status_code == 200
        assert status.json()["data"]["last_date"]
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


def test_prod_compose_and_image_carry_card_support():
    compose = (ROOT / "deploy/prod/docker-compose.server.yml").read_text(encoding="utf-8")
    for var in (
        "CHRONICLE_CARD_ENABLED",
        "CHRONICLE_CARD_PUBLISH_HOUR_HKT",
        "CHRONICLE_CARD_API_PREFIX",
        "CHRONICLE_CARD_WEBHOOK_URLS",
        "CHRONICLE_CARD_WEBHOOK_TYPE",
    ):
        keys = re.findall(rf"^\s+{var}:", compose, flags=re.MULTILINE)
        assert len(keys) == 2, (var, keys)  # city-api + city-worker
    assert "fonts-noto-cjk" in (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    assert "Pillow" in (ROOT / "backend/requirements.txt").read_text(encoding="utf-8")
    env_example = (ROOT / "deploy/prod/.env.example").read_text(encoding="utf-8")
    assert "CHRONICLE_CARD_WEBHOOK_URLS=" in env_example
    assert "KIMI_API_KEY=" not in env_example.replace("# KIMI_API_KEY=", "")


def test_readme_no_longer_claims_a_leaked_kimi_key():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "previously committed in plaintext" not in readme
    assert "Revoke and rotate it" not in readme
    assert "no `KIMI_API_KEY`" in readme
