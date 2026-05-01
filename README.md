# NachoMUD

An open-source text MUD with a procedurally generated world. Four AI
agents play continuously alongside human players — anyone can drop in
and watch them, sign in by email to claim their own character, and
explore a town that keeps growing every time someone wanders past an
unexplored exit.

The Dungeon Master is an LLM. Every new room is generated on demand
and frozen into the world forever; NPCs follow daily routines and
converse via LLM; combat is turn-based 5e (d20 + stat mod + prof
bonus vs AC); free-form actions ("I push the bookcase", "I bluff the
guard") get adjudicated against your real stats.

Local-only by default — runs entirely on Ollama, no API keys.

## Quick start

```bash
git clone https://github.com/bush-codes/nachomud
cd nachomud
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Make sure Ollama is installed: https://ollama.com
NACHOMUD_AUTH_DEV_ECHO=1 NACHOMUD_DISABLE_AGENTS=1 ./run.sh
# → open http://localhost:4000
```

`run.sh` starts Ollama, pulls the two models on first run (~8 GB
total), boots the FastAPI server, and serves the xterm.js terminal at
`/`.

`NACHOMUD_AUTH_DEV_ECHO=1` makes the magic-link sign-in print the
verify URL to the server log instead of trying to send email — handy
for local dev. `NACHOMUD_DISABLE_AGENTS=1` keeps the four built-in AI
agents from spinning up so you don't need an LLM running just to log
in.

## Models

Two Llama models out of the box:

| Role | Default | Override |
|---|---|---|
| Smart (DM, NPC dialogue, room gen) | `llama3.1:8b-instruct-q4_K_M` | `LLM_SMART_MODEL` |
| Fast (agent runner, summaries) | `llama3.2:3b` | `LLM_FAST_MODEL` |

Anything Ollama can serve will work — swap in `gemma2:9b`,
`qwen2.5:7b`, etc.

## Playing

Anonymous visitors land on a sidebar with five slots — your character
(grey, sign in to claim) plus four AI agents you can spectate by
clicking. Sign in by entering your email and clicking the link we
send. Once signed in, hit `n` (or Enter on a fresh install) to create
a character:

1. **Name** — alphanumerics, spaces, hyphens, apostrophes; max 24 chars.
2. **Race** — Human, Dwarf, Elf, Halfling, Half-Orc.
3. **Class** — Warrior, Paladin, Mage, Cleric, Ranger, Rogue.
4. **Stats** — 5e 27-point buy, or type `standard` for the standard array.
5. **Confirm** — see your final HP, AC, attack bonus, and starting abilities.

You spawn at the Bronze Hart Inn in Silverbrook.

## Commands

| Command | What it does |
|---|---|
| `look` (or `l`) | Describe the current room |
| `look <thing>` | DM narrates what you see |
| `n`/`s`/`e`/`w`/`u`/`d`, `north`, `go north` | Move |
| `exits` | List available exits |
| `inventory` (or `i`, `inv`) | Equipment + carried items |
| `stats` | Full character sheet |
| `map` | ASCII map with fog-of-war (only rooms you've visited) |
| `who` | Your name and class |
| `get <item>` / `drop <item>` | Pick up / drop |
| `attack <mob>` | Engage in combat |
| `talk <npc>` | Greet an NPC who's present right now |
| `tell <npc> <message>` | Say something specific |
| `dm <message>` | Chat with the Dungeon Master |
| `ask <question>` | Same as `dm` (alias) |
| `wait [Nm\|Nh]` | Pass time |
| `sleep` (or `rest`) | Sleep until 7am — full HP/MP. Sets respawn at inns. |
| `save` | Save now |
| `quit` | Disconnect |
| _anything else_ | Falls through to the DM as a free-form action |

## Combat

Initiative is rolled (1d20 + DEX). Your turn waits forever for input.

| Command | What it does |
|---|---|
| `attack <target>` | Basic attack (1d20 + attack bonus vs AC, weapon die + stat mod) |
| `<ability> [target]` | Class ability (e.g. `defend`, `smite goblin`, `heal`) |
| `look` / `status` | Combatants and stats |
| `flee` | Run. Engaged mobs each take a parting shot. |

Crits (nat 20) double the damage dice. Death drops you to your
respawn room with -10% XP.

## Self-hosting

NachoMUD has zero external dependencies in the default config —
Ollama on localhost handles every LLM call. To run it as a public
server:

- Set `NACHOMUD_SECRET_KEY` to a random 32+ byte string (used to sign
  session cookies).
- Configure SMTP for magic-link email:
  `NACHOMUD_SMTP_HOST` / `NACHOMUD_SMTP_PORT` /
  `NACHOMUD_SMTP_USER` / `NACHOMUD_SMTP_PASSWORD` /
  `NACHOMUD_MAIL_FROM`. The default points at Fastmail
  (`smtp.fastmail.com:465`). Bring your own SMTP provider.
- Set `NACHOMUD_SECURE_COOKIE=1` behind HTTPS.

See [`AGENTS.md`](AGENTS.md) for the full env-var list.

## Tests

```bash
pytest tests/             # full suite
pytest tests/world/       # one subdir
pytest tests/ -x          # stop at first failure
```

Tests use a seedable dice RNG (`dice.seed(N)`) and mock the LLM with
simple lambdas, so they run offline and deterministically. Set
`NACHOMUD_DISABLE_AGENTS=1` (the test fixtures do this for you) to
skip booting the four AI runners.

## Architecture

See [`AGENTS.md`](AGENTS.md) for the full architecture doc — package
layout, the WorldLoop / shared-world model, the auth flow, the DM,
combat math, classes & races, and contributor tasks.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). PRs welcome.

## License

MIT — see [`LICENSE`](LICENSE).
