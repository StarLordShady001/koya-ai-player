from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

CLOUDFLARE_AI_URL = os.getenv("CLOUDFLARE_AI_URL", "").rstrip("/")
CLOUDFLARE_AI_TOKEN = os.getenv("CLOUDFLARE_AI_TOKEN", "")
MAX_HISTORY = int(os.getenv("MAX_AI_HISTORY", "12"))
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "30"))

COMMAND_CATALOG = [
    "/adventure context", "/adventure guide", "/adventure tutorial", "/balance",
    "/battle start", "/battle stats", "/boat expedition start <name>",
    "/boat expedition list", "/boat expedition stats", "/boat crew view",
    "/boat crew level-up <name>", "/boat build", "/boat navigate", "/boat list",
    "/chapter view", "/chapter next", "/colosseum register", "/colosseum unregister",
    "/colosseum stats", "/crew", "/daily claim", "/daily check", "/daily stats",
    "/dendenmushi catch", "/dendenmushi check", "/dendenmushi stats",
    "/dendenmushi collection view", "/event", "/events", "/fish catch", "/fish menu",
    "/fish guide", "/fish voyage", "/fish codex", "/fish stats", "/fish inventory",
    "/fish shop", "/fish market", "/inventory view", "/inventory currency",
    "/inventory consumables", "/inventory lootbox", "/inventory quest",
    "/inventory cosmetics", "/inventory use <item>", "/logpose", "/lootbox list",
    "/lootbox open <name>", "/lootbox info", "/lootbox premium", "/profile view",
    "/quests view", "/quests stats", "/shop", "/shop battle",
    "/train haki <type> <points>", "/train weapon", "/train mastery", "/train stats",
    "/train list", "/vote check", "/vote rewards", "/wanted",
]

BLOCKED_AUTOMATION_PREFIXES = ("/adventure delete", "/premium", "/dice bet", "/casino bet", "/fleet transfer")

SYSTEM_PROMPT = """
You are the strategy engine for an AI agent playing Koya's One Piece World Tour Adventure game.

Inspect the supplied game state and recent observations, then choose exactly ONE best next action.

Priority:
1. Complete active chapter/story objectives.
2. Improve character power efficiently.
3. Maintain sustainable berries, cola, energy and other resources.
4. Keep passive/income activities productive.
5. Avoid unnecessary risk.

Rules:
- Never invent commands.
- Only select commands from the supplied command catalog.
- Prefer actions that advance multiple active goals.
- If information is incomplete or ambiguous, choose an inspection command.
- Learn from recent outcomes. Avoid blindly repeating failed actions, cooldowns, or actions that produced no progress.
- Never select premium spending, gambling, deletion, transfers, or other high-risk actions.
- Return exactly one action or null if waiting/inspection is preferable.

Return ONLY valid JSON matching the required decision fields.
"""

@dataclass
class Decision:
    action: str | None
    arguments: dict[str, Any]
    reason: str
    goal: str
    confidence: float
    risk: str
    expected_result: str
    state_updates: dict[str, Any]

def _strip_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()

class AIBrain:
    def __init__(self) -> None:
        if not CLOUDFLARE_AI_URL:
            raise RuntimeError("Missing CLOUDFLARE_AI_URL")
        if not CLOUDFLARE_AI_TOKEN:
            raise RuntimeError("Missing CLOUDFLARE_AI_TOKEN")

    def decide(self, game_state: dict[str, Any], recent_events: list[dict[str, Any]]) -> Decision:
        payload = {
            "game_state": game_state,
            "recent_events": recent_events[-MAX_HISTORY:],
            "available_commands": COMMAND_CATALOG,
            "automation_policy": {"blocked_prefixes": list(BLOCKED_AUTOMATION_PREFIXES), "executor_default": "advisory_only"},
        }
        headers = {
            "Authorization": f"Bearer {CLOUDFLARE_AI_TOKEN}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=AI_TIMEOUT) as client:
            response = client.post(CLOUDFLARE_AI_URL, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
        if not result.get('ok'):
            raise RuntimeError(result.get("error", "Cloudflare AI request failed"))
        choices = result.get('choices') or []
        content = None
        if choices:
            content = (choices[0].get('message') or {}).get('content')
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Cloudflare AI returned no decision content")
        data = json.loads(_strip_json(content))
        action = data.get('action')
        if action is not None:
            action = str(action).strip()
            allowed = any(action == cmd or action.startswith(cmd.split(' <')[0] + ' ') for cmd in COMMAND_CATALOG)
            if not allowed:
                raise ValueError(f"AI selected unsupported command: {action}")
            for blocked in BLOCKED_AUTOMATION_PREFIXES:
                if action.startswith(blocked):
                    raise ValueError(f"AI selected blocked action: {action}")
        return Decision(
            action=action,
            arguments=data.get('arguments') or {},
            reason=str(data.get('reason', '')),
            goal=str(data.get('goal', '')),
            confidence=max(0.0, min(1.0, float(data.get('confidence', 0.0)))),
            risk=str(data.get('risk', 'medium')),
            expected_result=str(data.get('expected_result', '')),
            state_updates=data.get('state_updates') or {},
        )
