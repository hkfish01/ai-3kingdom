"""部署設定的防回歸檢查。

事件引擎是「有期限、不可逆」的劇情來源，production 是否啟用全靠 compose
的環境變數預設值。這個測試避免有人不小心把預設改回 false 而無人察覺。
"""

import re
from pathlib import Path

COMPOSE_FILE = (
    Path(__file__).resolve().parents[2] / "deploy" / "prod" / "docker-compose.server.yml"
)


def _world_event_env(text: str, service: str) -> dict[str, str]:
    """取出單一 service 的 WORLD_EVENTS_* environment 設定（不依賴 PyYAML）。"""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"  {service}:"))
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if re.match(r"^  [a-z][a-z0-9_-]*:", lines[i])
        ),
        len(lines),
    )
    result = {}
    for line in lines[start:end]:
        match = re.match(r"^\s+(WORLD_EVENTS_[A-Z_]+):\s*(.+)$", line)
        if match:
            result[match.group(1)] = match.group(2).strip()
    return result


def test_world_events_enabled_by_default_in_prod_compose():
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    enabled_lines = [
        line.strip()
        for line in text.splitlines()
        if "WORLD_EVENTS_ENABLED:" in line
    ]
    # city-api 與 city-worker 兩個 service 都要帶到，缺一個就會有服務不推進事件。
    assert len(enabled_lines) == 2, enabled_lines
    assert all(
        line == "WORLD_EVENTS_ENABLED: ${WORLD_EVENTS_ENABLED:-true}"
        for line in enabled_lines
    ), enabled_lines


def test_api_and_worker_carry_identical_event_settings():
    """city-api 與 city-worker 必須拿到同一組設定，否則公開端點與實際推進會不一致。"""
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    api = _world_event_env(text, "city-api")
    worker = _world_event_env(text, "city-worker")
    assert len(api) == 6, api
    assert api == worker, {"city-api": api, "city-worker": worker}
    assert all(
        value.startswith("${") and ":-" in value for value in api.values()
    ), api  # 全部都有安全預設，舊 .env 不必加行也能啟動


def test_env_example_documents_the_default():
    example = COMPOSE_FILE.parent / ".env.example"
    text = example.read_text(encoding="utf-8")
    assert "WORLD_EVENTS_ENABLED=true" in text
    assert "WORLD_EVENTS_ENABLED=false" in text  # 關閉方式的說明仍在


def test_delegation_enabled_by_default_on_both_services():
    """1.35.0：委任結算在 worker，公開規則在 api，兩邊都要拿到同一個安全預設。"""
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    lines = [
        line.strip()
        for line in text.splitlines()
        if "DELEGATION_ENABLED:" in line
    ]
    assert len(lines) == 2, lines
    assert all(line == "DELEGATION_ENABLED: ${DELEGATION_ENABLED:-true}" for line in lines), lines

    example = COMPOSE_FILE.parent / ".env.example"
    doc = example.read_text(encoding="utf-8")
    assert "DELEGATION_ENABLED=true" in doc
    assert "DELEGATION_ENABLED=false" in doc
