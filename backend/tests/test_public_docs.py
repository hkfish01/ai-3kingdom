"""公開文件必須給外部 Agent 公網網址，不能給節點內部的 localhost。"""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_public_docs_never_leak_internal_city_base_url():
    assert "localhost" in settings.city_base_url  # 前提：本機設定確實是內部位址
    for path in ("/api.md", "/combat.md", "/reference.md", "/skill.md"):
        text = client.get(path).text
        assert settings.public_site_url in text, f"{path} 缺少公開網址"
        assert settings.city_base_url not in text, f"{path} 洩漏了內部位址"
        assert "http://localhost:10090" not in text, f"{path} 洩漏了 localhost:10090"


def test_public_doc_base_url_override(monkeypatch):
    monkeypatch.setattr(settings, "public_doc_base_url", "https://docs.example.org/")
    text = client.get("/reference.md").text
    assert "https://docs.example.org/api.md" in text
    assert "https://docs.example.org//" not in text  # trailing slash 要被去掉
