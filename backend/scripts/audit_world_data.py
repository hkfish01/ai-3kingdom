#!/usr/bin/env python3
"""唯讀稽核目前世界資料，輸出 JSON 報告。不會修改任何資料。

    cd backend
    PYTHONPATH=. python scripts/audit_world_data.py
    PYTHONPATH=. python scripts/audit_world_data.py --summary   # 只看摘要
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services.world_data_audit import audit_world_data  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="唯讀世界資料稽核（不修改資料）")
    parser.add_argument("--summary", action="store_true", help="只輸出 summary 與建議")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = audit_world_data(db)
    finally:
        db.close()

    if args.summary:
        report = {
            "generated_at": report["generated_at"],
            "read_only": report["read_only"],
            "summary": report["summary"],
            "recommendations": report["recommendations"],
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
