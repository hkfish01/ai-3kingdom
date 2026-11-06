"""短連結／點擊追蹤：冪等短碼、open redirect 防護、歸因、待發佇列與舊資料清理。"""

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Agent, City, User
from app.services import link_tracking as links
from app.services.chronicle_publish import (
    _webhook_payload,
    current_post_package,
    publish_daily_post,
)
from app.services.system_state import get_state, set_state

client = TestClient(app)

DAY = "2026-11-06"


def _set_raw(key: str, value: str) -> None:
    with SessionLocal() as db:
        set_state(db, key, value)
        db.commit()


def _seed() -> None:
    with SessionLocal() as db:
        db.add(City(name=settings.city_name, base_url="http://localhost:8000"))
        user = User(
            username="link_owner",
            email="link_owner@example.com",
            password_hash="x",
            is_admin=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(
            Agent(
                owner_user_id=user.id,
                name="連結諸侯",
                role="平民",
                home_city=settings.city_name,
                current_city=settings.city_name,
                infantry=60,
                archer=10,
                cavalry=5,
                martial=60,
            )
        )
        db.commit()


def _codes(date_str: str = DAY) -> dict[str, dict]:
    with SessionLocal() as db:
        return links.ensure_links(db, date_str, "/chronicle", "zh")


def test_short_codes_are_stable_per_day_channel_and_target():
    first = _codes()
    second = _codes()
    assert {c: v["channel"] for c, v in first.items()} == {
        c: v["channel"] for c, v in second.items()
    }
    assert len(set(first)) == len(links.CHANNELS)
    assert first[next(iter(first))]["url"].startswith(settings.public_site_url.rstrip("/") + "/s/")

    other_day = _codes("2026-11-07")
    assert not set(first) & set(other_day)

    with SessionLocal() as db:
        different_target = links._code(DAY, "x", "/audience")
    assert different_target != links._code(DAY, "x", "/chronicle")


def test_safe_target_rejects_open_redirects():
    for target in (
        "//evil.example/x",
        "https://evil.example",
        "/admin",
        "/settings",
        "/\\evil.example",
        "/chronicle\nhttps://evil.example",
        "chronicle",
        "",
    ):
        assert links._safe_target(target) is False, target
    for target in ("/", "/chronicle", "/audience", "/season", "/battle/replay/abc", "/chronicle?d=1"):
        assert links._safe_target(target) is True, target


def test_record_click_counts_humans_and_excludes_preview_bots():
    rows = _codes()
    code = next(c for c, m in rows.items() if m["channel"] == "x")

    assert links.record_click(SessionLocal(), code, "Mozilla/5.0 (Macintosh)") == "/chronicle"
    assert links.record_click(SessionLocal(), code, "Twitterbot/1.0") == "/chronicle"

    with SessionLocal() as db:
        entry = links._load_day(db, DAY)["links"][code]
        assert entry["clicks"] == 2
        assert entry["human_clicks"] == 1


def test_public_redirect_is_302_and_unknown_code_is_404():
    rows = _codes()
    code = next(c for c, m in rows.items() if m["channel"] == "threads")
    resp = client.get(f"/world/public/s/{code}", follow_redirects=False, headers={"User-Agent": "Mozilla/5.0"})
    assert resp.status_code == 302
    assert resp.headers["location"] == "/chronicle"

    assert client.get("/world/public/s/deadbeef", follow_redirects=False).status_code == 404
    assert client.get("/world/public/s/../../admin", follow_redirects=False).status_code in (404, 422)


def test_forged_index_cannot_redirect_to_external_site():
    code = "a" * links.CODE_LENGTH
    _set_raw(
        links._code_key(code),
        json.dumps({"date": DAY, "channel": "x", "target": "https://evil.example"}),
    )
    assert links.record_click(SessionLocal(), code, "Mozilla/5.0") is None


def test_tracked_package_keeps_original_fields_and_adds_per_channel_captions():
    _seed()
    base = {
        "date": DAY,
        "lang": "zh",
        "headline": "【史記・洛陽】",
        "caption": f"今日天下 → {settings.public_site_url.rstrip('/')}/chronicle",
        "caption_long": f"全文 → {settings.public_site_url.rstrip('/')}/chronicle",
        "hashtags": "#AI三國",
        "image_url": "https://example/card.png",
        "link": f"{settings.public_site_url.rstrip('/')}/chronicle",
    }
    with SessionLocal() as db:
        patched = links.tracked_package(db, base, "zh")

    for key, value in base.items():
        assert patched[key] == value, key
    assert patched["share_url"].startswith(settings.public_site_url.rstrip("/") + "/s/")
    assert set(patched["links"]) == set(links.CHANNELS)
    assert patched["links"]["x"]["url"] != patched["links"]["threads"]["url"]
    for meta in patched["links"].values():
        assert meta["url"] in meta["caption"]
        assert settings.public_site_url.rstrip("/") + "/chronicle" not in meta["caption"]


def test_current_post_package_exposes_tracking_fields():
    _seed()
    with SessionLocal() as db:
        package = current_post_package(db, "zh")
    assert package["link"].endswith("/chronicle")
    assert package["share_url"]
    assert "audience" in package["links"]
    assert package["links"]["audience"]["target"] == "/audience"
    assert package["tracking_note"]


def test_webhook_payload_has_links_without_breaking_legacy_fields():
    package = {
        "date": DAY,
        "headline": "標題",
        "caption": "短文案",
        "caption_long": "長文案",
        "hashtags": "#AI三國",
        "image_url": "https://example/card.png",
        "link": "https://example/chronicle",
        "share_url": "https://example/s/abc12345",
        "links": {"x": {"url": "https://example/s/abc12345", "caption": "短文案", "caption_long": "長文案"}},
    }
    payload = _webhook_payload(package, "generic")
    assert payload["text"] == "短文案" and payload["link"] == "https://example/chronicle"
    assert payload["share_url"] == "https://example/s/abc12345"
    assert payload["channel_captions"]["x"]["url"].endswith("abc12345")
    discord = _webhook_payload(package, "discord")
    assert discord["embeds"][0]["url"] == "https://example/s/abc12345"


def test_discord_payload_uses_the_webhook_channel_short_link():
    """Discord 是獨立通路：內文與 embed 都不能誤掛 X 的短碼。"""
    package = {
        "date": DAY,
        "headline": "標題",
        "caption": "三回合回放 → https://example.com/battle/replay/arena_1",
        "caption_long": "長文案",
        "hashtags": "#AI三國",
        "image_url": "https://example.com/card.png",
        "link": "https://example.com/chronicle",
        "share_url": "https://example.com/s/xxxx1111",
        "links": {
            "x": {
                "url": "https://example.com/s/xxxx1111",
                "caption": "X 文案",
                "caption_long": "X 長文案",
            },
            "webhook": {
                "url": "https://example.com/s/wwww2222",
                "caption": "三回合回放 → https://example.com/s/wwww2222",
                "caption_long": "長文案 → https://example.com/s/wwww2222",
            },
        },
    }
    payload = _webhook_payload(package, "discord")
    assert "wwww2222" in payload["content"]
    assert "xxxx1111" not in payload["content"]
    assert payload["embeds"][0]["url"] == "https://example.com/s/wwww2222"
    assert payload["embeds"][0]["image"]["url"] == "https://example.com/card.png"

    legacy = dict(package)
    legacy["links"] = {"x": package["links"]["x"]}
    assert _webhook_payload(legacy, "discord")["embeds"][0]["url"] == "https://example.com/s/xxxx1111"


def test_discord_payload_from_real_package_is_not_attributed_to_x():
    _seed()
    with SessionLocal() as db:
        package = current_post_package(db, "zh")
    payload = _webhook_payload(package, "discord")
    webhook = package["links"]["webhook"]
    assert payload["embeds"][0]["url"] == webhook["url"]
    assert payload["embeds"][0]["url"] != package["links"]["x"]["url"]
    assert payload["content"] == webhook["caption"]


def test_stats_aggregate_human_clicks_by_channel():
    rows = _codes()
    x = next(c for c, m in rows.items() if m["channel"] == "x")
    threads = next(c for c, m in rows.items() if m["channel"] == "threads")
    with SessionLocal() as db:
        links.record_click(db, x, "Mozilla/5.0")
        links.record_click(db, x, "Slackbot-LinkExpanding 1.0")
        links.record_click(db, threads, "Mozilla/5.0")
        result = links.stats(db, days=7)
    assert result["total_clicks"] == 3
    assert result["total_human_clicks"] == 2
    assert result["by_channel"]["x"] == 1
    assert result["by_channel"]["threads"] == 1
    assert len(result["per_day"]) == 7
    assert "爬蟲" in result["note"]


def test_publish_writes_outbox_and_recent_outbox_reads_it():
    _seed()
    with SessionLocal() as db:
        result = publish_daily_post(db, force=True)
        assert result["status"] in ("prepared", "sent")
        outbox = links.recent_outbox(db, days=7)
    today = [i for i in outbox["items"] if i["date"] == result["date"]]
    assert len(today) == 1
    item = today[0]
    assert item["headline"]
    assert item["share_url"]
    assert "webhook_url" not in item and "deliveries" not in item
    assert "jwt" not in json.dumps(item).lower()


def test_outbox_public_endpoint_omits_private_fields():
    resp = client.get("/world/public/links/outbox?days=7")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["days"] == 7
    assert len(body["items"]) == 7
    assert all("deliveries" not in i and "webhook_url" not in i for i in body["items"])


def test_admin_status_requires_token():
    assert client.get("/admin/links/status").status_code == 401


def test_old_buckets_and_indexes_are_pruned():
    old = "2026-01-01"
    _set_raw(links._day_key(old), json.dumps({"date": old, "links": {}}))
    _set_raw(links._outbox_key(old), json.dumps({"date": old, "status": "prepared"}))
    _set_raw(
        links._code_key("0" * links.CODE_LENGTH),
        json.dumps({"date": old, "channel": "x", "target": "/chronicle"}),
    )
    _codes(DAY)
    with SessionLocal() as db:
        assert get_state(db, links._day_key(old)) == ""
        assert get_state(db, links._outbox_key(old)) == ""
        assert get_state(db, links._code_key("0" * links.CODE_LENGTH)) == ""


def test_keep_days_constant_is_sane():
    assert links.KEEP_DAYS >= 7
    assert timedelta(days=links.KEEP_DAYS).days == 30


def test_deploy_files_keep_the_zero_credential_loop_documented():
    """純文字防呆：webhook 變數要真的傳進 worker，文件要留著設定方式。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    compose = (root / "deploy" / "prod" / "docker-compose.server.yml").read_text(encoding="utf-8")
    env_example = (root / "deploy" / "prod" / ".env.example").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    route = (root / "frontend" / "app" / "s" / "[code]" / "route.ts").read_text(encoding="utf-8")

    assert "CHRONICLE_CARD_WEBHOOK_URLS" in compose
    assert "CHRONICLE_CARD_WEBHOOK_TYPE" in compose
    assert "city-worker" in compose
    assert "Discord" in env_example and "force-recreate city-worker" in env_example
    assert "/share" in readme and "/s/{code}" in readme
    assert "/world/public/s/" in route and "status: 302" in route
    # 不能從代理後的請求網址組絕對 Location：會外洩 container 內部位址並造成 502。
    assert "Location: `/world/public/s/${safe}`" in route
    assert "new URL(" not in route
    assert "/admin/links/stats" in readme


def _admin_token() -> str:
    from app.auth import create_access_token

    with SessionLocal() as db:
        admin = User(
            username="link_admin",
            email="link_admin@example.com",
            password_hash="x",
            is_admin=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        return create_access_token(admin.id)


def test_admin_stats_requires_an_admin_token():
    assert client.get("/admin/links/stats").status_code == 401

    from app.auth import create_access_token

    _seed()
    non_admin = client.get(
        "/admin/links/stats",
        headers={"Authorization": f"Bearer {create_access_token(1)}"},
    )
    assert non_admin.status_code == 403


def test_admin_stats_breaks_down_by_date_channel_and_target():
    _seed()
    rows = _codes()
    code = next(c for c, m in rows.items() if m["channel"] == "x")
    links.record_click(SessionLocal(), code, "Mozilla/5.0 (Macintosh)")
    links.record_click(SessionLocal(), code, "Twitterbot/1.0")

    token = _admin_token()
    resp = client.get(
        "/admin/links/stats?days=7",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_clicks"] == 2
    assert data["total_human_clicks"] == 1
    assert data["by_channel"]["x"] == 1
    assert data["by_target"] == {"/chronicle": 1}
    today = next(p for p in data["per_day"] if p["date"] == DAY)
    assert today["by_target"] == {"/chronicle": 1}
    row = next(r for r in today["rows"] if r["channel"] == "x")
    assert row["target"] == "/chronicle"
    assert row["clicks"] == 2 and row["human_clicks"] == 1
    assert data["top_links"][0]["code"] == code
    assert "visitor_id" not in json.dumps(data)
    assert "user_agent" not in json.dumps(data)

    # 公開版維持只有聚合數字，不洩漏逐日明細。
    public = client.get("/world/public/links/stats?days=7").json()["data"]
    assert "top_links" not in public and "by_target" not in public
    assert all("rows" not in p for p in public["per_day"])
