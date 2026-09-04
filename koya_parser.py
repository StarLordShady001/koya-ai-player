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


def _chapter_meta(text: str) -> dict[str, Any]:
    m = re.search(
        r"(?i)\bChapter\s+(\d+)\s*/\s*(\d+)\s*:\s*([^\n]+)",
        text,
    )
    if not m:
        return {}
    return {
        "chapter_number": int(m.group(1)),
        "chapter_total": int(m.group(2)),
        "chapter_name": m.group(3).strip(),
    }


def _objective_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    patterns = [
        re.compile(r"(?i)collect\s+([0-9][0-9,]*)\s+berries[^\n]*?([0-9][0-9,]*)\s*/\s*([0-9][0-9,]*)"),
        re.compile(r"(?i)buy\s+([0-9][0-9,]*)\s+combat\s+items?[^\n]*?([0-9][0-9,]*)\s*/\s*([0-9][0-9,]*)"),
    ]

    labels = ["berries", "combat_item"]

    for pattern, label in zip(patterns, labels):
        m = pattern.search(text)
        if not m:
            continue
        required_word = int(m.group(1).replace(",", ""))
        current = int(m.group(2).replace(",", ""))
        required_progress = int(m.group(3).replace(",", ""))
        records.append({
            "type": label,
            "required": required_word,
            "current": current,
            "progress_required": required_progress,
            "complete": current >= required_progress,
        })

    return records


def parse_observation(text: str) -> dict[str, Any]:
    state: dict[str, Any] = {
        "raw": text[:12000],
        "energy": _num(text, "energy"),
        "health": _num(text, "health") or _num(text, "hp"),
        "berries": _num(text, "berries") or _num(text, "berry"),
        "cola": _num(text, "cola"),
        "fish_coins": _num(text, "fish coins"),
        "level": _num(text, "level"),
    }

    state.update(_chapter_meta(text))

    progress_matches = [
        int(m.group(1))
        for m in re.finditer(r"(?i)\b(\d{1,3})\s*%\b", text)
        if 0 <= int(m.group(1)) <= 100
    ]
    if progress_matches:
        state["progress_percent"] = progress_matches[0]

    objectives = _objective_records(text)
    if objectives:
        state["objectives"] = objectives

    return state
