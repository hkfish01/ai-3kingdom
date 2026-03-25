from pathlib import Path

from app.error_messages import ERROR_MESSAGES


def generate_markdown() -> str:
    lines = ["# API Error Codes", "", "Generated from `backend/app/error_messages.py`.", "", "| Code | Message |", "|---|---|"]
    for code in sorted(ERROR_MESSAGES.keys()):
        msg = ERROR_MESSAGES[code].replace("|", "\\|")
        lines.append(f"| `{code}` | {msg} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "error-codes.md"
    out.write_text(generate_markdown(), encoding="utf-8")
    print(f"Error code document exported to {out}")
