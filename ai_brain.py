from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")
MAX_HISTORY = int(os.getenv("MAX_AI_HISTORY", "12"))

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

BLOCKED_AUTOMATION_PREFIXES = (
    "/adventure delete", "/premium", "/dice bet", "/casino bet", "/fleet transfer",
)

SYSTEM_PROMPT = """
You are the strategy engine for an AI agent playing Koya's One Piece World Tour
Adventure game. Your job is to understand the player's current state, chapter
story/goals, resources, cooldowns and recent outcomes, then choose the next
single best action.

Important behavior:
- Optimize for chapter/story progression first, then character power, then sustainable resources and passive income.
- Prefer actions that satisfy multiple active goals at once.
- Never invent a command. Select only from the supplied command catalog.
- Never choose premium spending, deleting a profile, gambling, transfers, or other risky actions unless an authorized executor policy explicitly permits it.
- Treat ambiguous Koya output as uncertain. When uncertain, inspect state with a view/stats/context command instead of guessing.
- Learn from outcomes. If an action produced no progress, an error, a cooldown, or unexpected resource cost, update the strategy and avoid blindly repeating it.
- Keep actions granular: return one next action, not a long batch.
- You may recommend waiting when the current state is blocked by cooldown, missing energy, or an active expedition; represent that with action=null.

Return ONLY valid JSON matching this schema:
{
  "action": string|null,
  "arguments": object,
  "reason": string,
  "goal": string,
  "confidence": number,
  "risk": "low"|"medium"|"high",
  "expected_result": string,
  "state_updates": object
}
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
        self.client = OpenAI()

    def decide(self, game_state: dict[str, Any], recent_events: list[dict[str, Any]]) -> Decision:
        payload = {
            "game_state": game_state,
            "recent_events": recent_events[-MAX_HISTORY:],
            "available_commands": COMMAND_CATALOG,
            "automation_policy": {
                "blocked_prefixes": BLOCKED_AUTOMATION_PREFIXES,
                "executor_default": "advisory_only",
            },
        }
        response = self.client.responses.create(
            model=MODEL,
            instructions=SYSTEM_PROMPT,
            input=json.dumps(payload, ensure_ascii=False),
            store=False,
        )
        raw = _strip_json(response.output_text)
        data = json.loads(raw)
        action = data.get("action")
        if action:
            normalized = action.strip()
            if not any(normalized == cmd or normalized.startswith(cmd.split(" <")[0]) for cmd in COMMAND_CATALOG):
                raise ValueError(f"AI selected unsupported command: {action}")
            for blocked in BLOCKED_AUTOMATION_PREFIXES:
                if normalized.startswith(blocked):
                    raise ValueError(f"AI selected blocked action: {action}")
            action = normalized
        return Decision(
            action=action,
            arguments=data.get("arguments") or {},
            reason=str(data.get("reason", "")),
            goal=str(data.get("goal", "")),
            confidence=max(0.0, min(1.0, float(data.get("confidence", 0.0)))),
            risk=str(data.get("risk", "medium")),
            expected_result=str(data.get("expected_result", "")),
            state_updates=data.get("state_updates") or {},
        )
