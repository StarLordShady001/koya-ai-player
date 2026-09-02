from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

from ai_brain import AIBrain, Decision
from executor import Executor
from koya_parser import extract_message_text, parse_observation
from state_store import get_session, read_state, recent_events, save_event, update_session, write_state

KOYA_BOT_ID = int(os.getenv("KOYA_BOT_ID", "0")) or None
KOYA_NAME_PATTERN = os.getenv("KOYA_NAME_PATTERN", r"(?i)^koya(?:#|$)")
ANALYSIS_COOLDOWN = float(os.getenv("ANALYSIS_COOLDOWN", "2.5"))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.75"))
MAX_MESSAGES_PER_MINUTE = int(os.getenv("MAX_MESSAGES_PER_MINUTE", "12"))

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

brain = AIBrain()
executor = Executor()


def is_koya(message: discord.Message) -> bool:
    if not message.author.bot:
        return False
    if KOYA_BOT_ID and message.author.id == KOYA_BOT_ID:
        return True
    return bool(re.match(KOYA_NAME_PATTERN, message.author.name or ""))


def normalize_state(previous: dict, observation: dict, decision: Optional[Decision]) -> dict:
    state = dict(previous)
    for key, value in observation.items():
        if key != "raw" and value is not None:
            state[key] = value
    state["last_observation"] = observation.get("raw", "")[:4000]
    if decision:
        state.setdefault("learning", {})
        state["learning"].update(decision.state_updates)
        state["learning"]["last_reason"] = decision.reason
        state["learning"]["last_goal"] = decision.goal
        state["learning"]["last_action"] = decision.action
    return state


class AgentBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents)
        self.rate_window: dict[tuple[int, int], list[float]] = {}
        self.session_locks: dict[tuple[int, int], asyncio.Lock] = {}
        self.guild_commands_synced = False

    async def setup_hook(self) -> None:
        # Keep global registration as the production/default command set.
        await self.tree.sync()

    async def sync_guild_commands(self) -> None:
        # Guild commands propagate immediately, which is useful for local testing.
        # We copy the globally defined commands into every guild this bot is in.
        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        self.guild_commands_synced = True

    def lock_for(self, guild_id: int, user_id: int) -> asyncio.Lock:
        key = (guild_id, user_id)
        return self.session_locks.setdefault(key, asyncio.Lock())

    def allowed_by_rate(self, guild_id: int, user_id: int) -> bool:
        now = time.time()
        key = (guild_id, user_id)
        values = [t for t in self.rate_window.get(key, []) if now - t < 60]
        if len(values) >= MAX_MESSAGES_PER_MINUTE:
            self.rate_window[key] = values
            return False
        values.append(now)
        self.rate_window[key] = values
        return True

bot = AgentBot()


@bot.event
async def on_ready():
    if not bot.guild_commands_synced:
        await bot.sync_guild_commands()
    print(f"Koya AI Player online as {bot.user} | executor={executor.mode} | guild_commands_synced={bot.guild_commands_synced}")


@bot.tree.command(name="navigator", description="Control the adaptive Koya AI player.")
@app_commands.describe(action="on, off, status, or mode")
@app_commands.choices(action=[
    app_commands.Choice(name="on", value="on"),
    app_commands.Choice(name="off", value="off"),
    app_commands.Choice(name="status", value="status"),
    app_commands.Choice(name="mode", value="mode"),
])
async def navigator(interaction: discord.Interaction, action: app_commands.Choice[str]):
    if not interaction.guild:
        await interaction.response.send_message("Use this inside a server.", ephemeral=True); return
    gid, uid = interaction.guild.id, interaction.user.id
    s = get_session(gid, uid)
    if action.value == "status":
        decision = json.loads(s["last_decision_json"] or "{}")
        await interaction.response.send_message(
            f"AI Player: **{'ON' if s['enabled'] else 'OFF'}**\n"
            f"Mode: **{s['mode']}**\n"
            f"Last action: `{decision.get('action') or 'none'}`\n"
            f"Confidence: `{decision.get('confidence', '-')}`",
            ephemeral=True,
        )
    elif action.value == "mode":
        await interaction.response.send_message(
            f"Current mode: **{s['mode']}**. Set `AGENT_MODE=advisory` or use an authorized executor endpoint; normal Discord user-account automation is not supported.",
            ephemeral=True,
        )
    else:
        update_session(gid, uid, enabled=1 if action.value == "on" else 0)
        await interaction.response.send_message(
            f"Adaptive AI Player **{'ON' if action.value == 'on' else 'OFF'}**.", ephemeral=True
        )


@bot.tree.command(name="next", description="Show the AI's current next action.")
async def next_action(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Use this inside a server.", ephemeral=True); return
    s = get_session(interaction.guild.id, interaction.user.id)
    d = json.loads(s["last_decision_json"] or "{}")
    if not d:
        await interaction.response.send_message("No decision yet. Turn the navigator on and generate a Koya update.", ephemeral=True); return
    await interaction.response.send_message(
        f"**Next:** `{d.get('action') or 'wait/inspect'}`\n"
        f"**Goal:** {d.get('goal','')}\n"
        f"**Why:** {d.get('reason','')}\n"
        f"**Confidence:** {d.get('confidence','-')} | **Risk:** {d.get('risk','-')}", ephemeral=True
    )


@bot.tree.command(name="state", description="Show the AI player's learned game state.")
async def state_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Use this inside a server.", ephemeral=True); return
    state = read_state(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"```json\n{json.dumps(state, indent=2)[:3800]}\n```", ephemeral=True)


async def analyze_for_user(message: discord.Message, user_id: int) -> None:
    gid = message.guild.id
    key_lock = bot.lock_for(gid, user_id)
    async with key_lock:
        session = get_session(gid, user_id)
        if not session["enabled"]:
            return
        text = extract_message_text(message)
        if not text:
            return
        save_event(gid, user_id, "koya", text)
        observation = parse_observation(text)
        previous_state = read_state(gid, user_id)
        write_state(gid, user_id, normalize_state(previous_state, observation, None))
        if not bot.allowed_by_rate(gid, user_id):
            return
        try:
            decision = await asyncio.to_thread(brain.decide, read_state(gid, user_id), recent_events(gid, user_id))
        except Exception as exc:
            update_session(gid, user_id, last_decision_json=json.dumps({"error": str(exc), "ts": time.time()}))
            await message.channel.send(f"🧭 **AI Player:** analysis failed safely: `{type(exc).__name__}`. No action was executed.")
            return
        state = normalize_state(previous_state, observation, decision)
        write_state(gid, user_id, state)
        update_session(gid, user_id, last_decision_json=json.dumps({
            "action": decision.action,
            "arguments": decision.arguments,
            "reason": decision.reason,
            "goal": decision.goal,
            "confidence": decision.confidence,
            "risk": decision.risk,
            "expected_result": decision.expected_result,
        }, ensure_ascii=False))

        if not decision.action:
            msg = f"🧭 **AI Player:** wait / inspect. {decision.reason}"
        else:
            command = decision.action
            if decision.arguments:
                args = " ".join(f"{k}={v}" for k, v in decision.arguments.items())
                command = f"{command} {args}"
            if decision.confidence < MIN_CONFIDENCE or decision.risk == "high":
                msg = f"🧭 **AI Player → HOLD**\nProposed: `{command}`\nReason: {decision.reason}\nConfidence: {decision.confidence:.2f}"
            else:
                result = await executor.execute(decision.action, decision.arguments)
                if result.get("status") == "advisory":
                    msg = f"🧭 **AI Player → {command}**\n{decision.reason}\nConfidence: {decision.confidence:.2f}\n_Advisory: no Discord user-account command was sent._"
                else:
                    msg = f"🧭 **AI Player → EXECUTED VIA AUTHORIZED ADAPTER**\n`{command}`\n{decision.reason}\nResult: `{result.get('status','ok')}`"
        await message.channel.send(msg[:1900])


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or not message.guild or not is_koya(message):
        return
    con = __import__("sqlite3").connect(os.getenv("DB_PATH", "koya_ai_player.db"))
    rows = con.execute("SELECT user_id FROM agent_sessions WHERE guild_id=? AND enabled=1", (message.guild.id,)).fetchall()
    con.close()
    for (user_id,) in rows:
        await analyze_for_user(message, user_id)


TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("Missing DISCORD_TOKEN")

bot.run(TOKEN)
