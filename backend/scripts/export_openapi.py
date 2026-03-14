import json
from pathlib import Path

from app.main import app


if __name__ == "__main__":
    out_path = Path(__file__).resolve().parent.parent / "openapi.json"
    out_path.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    print(f"OpenAPI spec exported to {out_path}")
