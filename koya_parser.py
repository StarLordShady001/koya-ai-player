from __future__ import annotations

import re
from typing import Any


def extract_message_text(message) -> str:
    parts: list[str] = []
    if getattr(message, "content", None):
        parts.append(message.content)
    for embed in getattr(message, "embeds", []) or []:
        for attr in ("title", "description", "footer"):
            value = getattr(embed, attr, None)
            if value:
                if attr == "footer" and hasattr(value, "text"):
                    value = value.text
                parts.append(str(value))
        for field in getattr(embed, "fields", []) or []:
            parts.append(f"{field.name}: {field.value}")
    return "\n".join(p for p in parts if p).strip()


def _num(text: str, label: str) -> int | None:
    m = re.search(rf"(?i)\b{re.escape(label)}\b\s*[:=]?\s*([0-9][0-9,]*)", text)
    return int(m.group(1).replace(",", "")) if m else None


def _chapter(text: str) -> str | None:
    m = re.search(r"(?i)\bchapter\b\s*[:#-]?\s*([^\n|]+)", text)
    return m.group(1).strip() if m else None


def parse_observation(text: str) -> dict[str, Any]:
    return {
        "raw": text[:12000],
        "chapter": _chapter(text),
        "progress_percent": next((int(m.group(1)) for m in re.finditer(r"(?i)\b(\d{1,3})\s*%", text) if int(m.group(1)) <= 100), None),
        "energy": _num(text, "energy"),
        "health": _num(text, "health") or _num(text, "hp"),
        "berries": _num(text, "berries") or _num(text, "berry"),
        "cola": _num(text, "cola"),
        "fish_coins": _num(text, "fish coins"),
        "level": _num(text, "level"),
    }
