from __future__ import annotations

import re
from typing import Any


def extract_message_text(message) -> str:
    parts: list[str] = []
    if getattr(message, 'content', None):
        parts.append(message.content)
    for embed in getattr(message, 'embeds', []) or []:
        for attr in ('title', 'description', 'footer'):
            value = getattr(embed, attr, None)
            if value:
                if attr == 'footer' and hasattr(value, 'text'):
                    value = value.text
                parts.append(str(value))
        for field in getattr(embed, 'fields', []) or []:
            parts.append(f'{field.name}: {field.value}')
    return '\n'.join(p for p in parts if p).strip()


def _num(text: str, label: str) -> int | None:
    m = re.search(rf'(?i)\b{re.escape(label)}\b\s*[:=]?\s*([0-9][0-9,]*)', text)
    return int(m.group(1).replace(',', '')) if m else None


def _chapter_meta(text: str) -> dict[str, Any]:
    m = re.search(
        r'(?i)\bChapter\s+(\d+)\s*/\s*(\d+)\s*:\s*([^\n]+)',
        text,
    )
    if not m:
        return {}
    return {
        'chapter_number': int(m.group(1)),
        'chapter_total': int(m.group(2)),
        'chapter_name': m.group(3).strip(),
    }


def _parse_objectives(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    # Koya commonly renders objectives as:
    # Collect 500 berries: 500/500 (100%)
    # Buy 1 combat items from the shop: 0/1 (0%)
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip('•-*').strip()
        if re.match(r'(?i)^chapter\s+\d+\s*/\s*\d+', line):
            continue
        if not re.search(r'\b\d+\s*/\s*\d+\b', line):
            continue
        if not re.search(r'\(\s*\d{1,3}\s*%\s*\)', line):
            continue

        progress = re.search(r'(\d[\d,]*)\s*/\s*(\d[\d,]*)', line)
        if not progress:
            continue
        current = int(progress.group(1).replace(',', ''))
        required = int(progress.group(2).replace(',', ''))
        complete = current >= required

        lower = line.lower()
        if 'combat item' in lower:
            objective_type = 'combat_item'
        elif 'berries' in lower:
            objective_type = 'berries'
        elif 'cola' in lower:
            objective_type = 'cola'
        elif 'fish coin' in lower:
            objective_type = 'fish_coins'
        elif 'experience' in lower or re.search(r'\bxp\b', lower):
            objective_type = 'experience'
        elif 'recruit' in lower and 'crew' in lower:
            objective_type = 'recruit_crew'
        elif 'crew' in lower:
            objective_type = 'crew'
        elif 'weapon' in lower:
            objective_type = 'weapon'
        elif 'mastery' in lower:
            objective_type = 'mastery'
        elif 'haki' in lower:
            objective_type = 'haki'
        elif 'battle' in lower or 'win' in lower:
            objective_type = 'battle'
        else:
            objective_type = 'other'

        records.append({
            'type': objective_type,
            'text': line,
            'current': current,
            'required': required,
            'complete': complete,
        })

    return records


def parse_observation(text: str) -> dict[str, Any]:
    state: dict[str, Any] = {
        'raw': text[:12000],
        'energy': _num(text, 'energy'),
        'health': _num(text, 'health') or _num(text, 'hp'),
        'berries': _num(text, 'berries') or _num(text, 'berry'),
        'cola': _num(text, 'cola'),
        'fish_coins': _num(text, 'fish coins'),
        'level': _num(text, 'level'),
    }

    state.update(_chapter_meta(text))

    progress_matches = [
        int(m.group(1))
        for m in re.finditer(r'(?i)\b(\d{1,3})\s*%\b', text)
        if 0 <= int(m.group(1)) <= 100
    ]
    if progress_matches:
        state['progress_percent'] = progress_matches[0]

    objectives = _parse_objectives(text)
    if objectives:
        state['objectives'] = objectives

    return state
