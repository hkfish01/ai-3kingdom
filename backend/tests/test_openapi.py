from app.main import app


def test_openapi_contains_core_paths():
    spec = app.openapi()
    paths = spec.get("paths", {})
    assert "/world/manifest" in paths
    assert "/federation/v1/hello" in paths
    assert "/social/faction/create" in paths
