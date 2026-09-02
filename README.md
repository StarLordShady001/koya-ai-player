# Koya Adaptive AI Player — Beta

Adaptive AI strategy companion for Koya's One Piece World Tour Adventure. It observes Koya messages/embeds, stores persistent game state and recent outcomes, asks an OpenAI reasoning model for one next action, validates that action against a curated Koya Adventure command allowlist, and logs the decision.

## Included

### AI player
- `bot.py` — Discord application bot and observation loop
- `ai_brain.py` — OpenAI Responses API strategy engine and command validation
- `koya_parser.py` — Koya message/embed parser
- `state_store.py` — SQLite state and event history
- `executor.py` — advisory mode plus an authorized HTTP adapter
- `requirements.txt` — Python dependencies
- `.env.example` — configuration template
- `Dockerfile` / `docker-compose.yml` — container deployment

### Website / legal
- `index.html` — project landing page
- `terms.html` — Terms of Service
- `privacy.html` — Privacy Policy
- `cloudflare-worker.js` — Cloudflare Worker health endpoint

## What it does

- `/navigator on` and `/navigator off` control the AI player.
- `/navigator status` shows status and the latest AI decision.
- `/next` shows the latest recommended action.
- `/state` shows persisted learned game state.
- Reads Koya bot message text and embeds.
- Sends state + recent observations to the OpenAI Responses API.
- Returns one granular action with reason, confidence, risk, expected result and state updates.
- Learns from later Koya outcomes through persistent event history and state updates.
- Defaults to **advisory mode** and does not automate a normal Discord user account.

## Architecture

```text
Koya message/embed
       ↓
Discord Bot Observer
       ↓
Parser → SQLite state/event log
       ↓
OpenAI Responses API
       ↓
Decision validator / risk policy
       ↓
Advisory output OR authorized HTTP executor
       ↓
Koya result → observer → learning loop
```

## Setup

1. Create a Discord application and bot in the Discord Developer Portal.
2. Install that bot in the server where Koya is installed, with only the channel permissions it needs.
3. Enable Message Content Intent for the bot because the observer reads Koya text/embeds.
4. Create an OpenAI API key and configure `OPENAI_API_KEY`.
5. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN`, `KOYA_BOT_ID`, and `OPENAI_API_KEY`.
6. Install and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python bot.py
```

7. In Discord, run `/navigator on`.

## Recommended first test

Keep `EXECUTOR_MODE=advisory`. Use Koya normally and let the AI inspect updates. A simple flow is:

```text
/navigator on
/adventure context
/chapter view
```

Then perform the recommended Koya action manually and let the bot observe the result. Check `/state` and `/next`.

## Authorized execution adapter

A true autonomous executor is only appropriate for an explicitly authorized game/vendor/test API. Configure:

```text
EXECUTOR_MODE=http
EXECUTOR_BASE_URL=https://your-authorized-test-host
EXECUTOR_TOKEN=...
```

The adapter sends `POST /actions` with JSON containing `command` and `arguments`. It is intentionally **not** a Discord user-account automation client.

## Safety / policy defaults

The AI is blocked from selecting actions such as adventure deletion, premium spending, gambling, or fleet transfers. High-risk or low-confidence recommendations are held. Do not use a normal Discord user token; use an official Discord bot/application account.

## Production hardening

- Move SQLite to PostgreSQL for multi-instance deployments.
- Add per-channel allowlists and admin-only controls.
- Add an approval workflow for medium-risk actions.
- Add screenshot/vision parsing for UI-heavy game state.
- Store action/result pairs for offline evaluation.
- Add a replay/evaluation harness.
- Add a vendor-provided test API adapter if autonomous execution is officially supported.
