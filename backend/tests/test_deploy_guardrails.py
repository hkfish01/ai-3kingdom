"""Deployment guardrails.

Two real incidents motivated these checks:

1. Running a bare `docker compose up` on the server picked the root (dev)
   compose file, whose container names were identical to the production ones.
   It failed with "container name /ai3k-redis is already in use" and would have
   overwritten live settings with dev defaults had it succeeded.
2. proxy_pass with a static hostname resolves only once when nginx starts, so
   recreating city-api left nginx pointing at a stale IP and /api/ returned 502.

The checks are deliberately text-based: CI installs only
backend/requirements.txt, which has no PyYAML.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV_COMPOSE = ROOT / "docker-compose.yml"
PROD_COMPOSE = ROOT / "deploy" / "prod" / "docker-compose.server.yml"
NGINX_CONF = ROOT / "deploy" / "prod" / "nginx.conf"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _container_names(text: str) -> list[str]:
    return re.findall(r"^\s*container_name:\s*(\S+)", text, flags=re.MULTILINE)


def _service_names(text: str) -> set[str]:
    # Only the two-space-indented keys in the services block are service names.
    block = text.split("services:", 1)[1]
    return set(re.findall(r"^  ([a-z][a-z0-9-]*):\s*$", block, flags=re.MULTILINE))


def test_dev_compose_has_no_obsolete_version():
    assert not re.search(r"^version:", _text(DEV_COMPOSE), flags=re.MULTILINE)


def test_dev_and_prod_container_names_cannot_collide():
    dev = _container_names(_text(DEV_COMPOSE))
    prod = _container_names(_text(PROD_COMPOSE))
    assert len(dev) == 6
    assert len(prod) == 6
    assert all(name.startswith("ai3k-dev-") for name in dev), dev
    assert all(not name.startswith("ai3k-dev-") for name in prod), prod
    assert set(dev).isdisjoint(prod)


def test_dev_compose_never_joins_the_production_network():
    text = _text(DEV_COMPOSE)
    assert "prod_default" not in text
    assert "external: true" not in text
    assert re.search(r"^networks:\n  dev_default:", text, flags=re.MULTILINE)
    assert text.count("- dev_default") == 6
    assert text.count("- prod_default") == 0


def test_dev_compose_does_not_bind_the_production_gateway_port():
    text = _text(DEV_COMPOSE)
    assert '"10090:80"' not in text
    assert '${DEV_GATEWAY_PORT:-10091}:80' in text


def test_dev_gateway_config_mount_is_not_hardcoded_to_one_users_home():
    text = _text(DEV_COMPOSE)
    assert "/home/" not in text
    assert "./deploy/prod/nginx.conf:/etc/nginx/conf.d/default.conf:ro" in text


def test_nginx_resolves_upstreams_through_docker_dns():
    text = _text(NGINX_CONF)
    assert "resolver 127.0.0.11" in text
    assert "valid=10s" in text
    assert "ipv6=off" in text
    # Static hostnames are the bug: nginx caches their IP until it restarts.
    assert "proxy_pass http://city-api:8000" not in text
    assert "proxy_pass http://ai3k-frontend:3000" not in text
    assert "ai3k-frontend" not in text
    assert 'set $api_backend "city-api:8000";' in text
    assert 'set $frontend_backend "frontend:3000";' in text


def test_nginx_keeps_the_public_routing_contract():
    text = _text(NGINX_CONF)
    assert "location = /health" in text
    assert "location /api/" in text
    assert "location /world/" in text
    assert "rewrite ^/api/(.*)$ /$1 break;" in text
    assert "proxy_pass http://$api_backend/health;" in text
    assert "proxy_pass http://$api_backend;" in text
    assert "proxy_pass http://$frontend_backend;" in text
    # Building the URL from $uri / $request_uri would break percent-encoding;
    # leave the URI handling to nginx by keeping proxy_pass without a URI part.
    assert "$uri$is_args$args" not in text
    assert "$request_uri" not in text
    assert "proxy_set_header Upgrade $http_upgrade;" in text
    assert 'proxy_set_header Connection "upgrade";' in text
    # Cheap syntax smoke test for machines without nginx installed.
    assert text.count("{") == text.count("}")


def test_both_compose_files_expose_the_service_names_nginx_looks_up():
    dev = _service_names(_text(DEV_COMPOSE))
    prod = _service_names(_text(PROD_COMPOSE))
    for name in ("city-api", "frontend", "postgres", "redis", "gateway"):
        assert name in dev, (name, sorted(dev))
        assert name in prod, (name, sorted(prod))
