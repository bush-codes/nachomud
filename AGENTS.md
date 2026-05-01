# NachoMUD — Architecture for AI assistants

Canonical architecture doc for AI coding assistants working on this
project. Human contributors should also read it but may prefer
[`README.md`](./README.md) and [`CONTRIBUTING.md`](./CONTRIBUTING.md) first.

When you change architecture, mechanics, prompt structure, or anything
documented here, **update this file**.

## North star — apply on every change

**1. Commit in logical chunks as you go.** Don't accumulate hours of
work in the working tree without committing. Every meaningful unit of
work — finished a refactor stage, made tests pass after a fix, completed
a small feature — gets a commit. This is the ONLY recovery path if
something goes wrong (stray `git checkout`, accidental `rm`, IDE
crash). The author of this doc lost a session of work to one careless
checkout. Don't repeat that.

**2. SWE hygiene.** Apply standard principles — DRY, single
responsibility, clear naming. Don't add abstractions beyond what the
change requires. Don't add error handling for impossible cases. Default
to no comments; write one only when the *why* is non-obvious.

**3. Code-smell sweep.** On the touched code (and broader when touching
shared modules):

```bash
ruff check --select F,B,SIM,UP,C4,RET,PIE,PT,PERF,RUF,E,W \
    --ignore E501,RUF012,UP007,UP045,UP046 nachomud/
ruff check --select F,B,SIM,UP,C4,RET,PIE,PT,PERF,RUF,E,W \
    --ignore E501,RUF012,UP007,UP045,UP046 --fix --unsafe-fixes nachomud/
```

Triage what remains. Don't auto-suppress findings; either fix or
explicitly justify per-line with `# noqa:` and a reason.

**4. Security review.** On every change touching auth, I/O,
deserialization, command dispatch, or external services:

```bash
bandit -r nachomud/                  # SAST
pip-audit -r requirements.txt        # CVEs in deps
```

`bandit -ll` (medium+) must come back clean. Auth code must use
`secrets`, not `random` — `nachomud/auth/magic_link.py` is the
reference.

**5. Tests.** `pytest tests/` must pass before commit. Add tests for
new public surface; mock LLM calls with `lambda s, u: "..."`; seed dice
with `dice.seed(...)`. The agent runner is disabled in tests via
`NACHOMUD_DISABLE_AGENTS=1`.

**6. Update this file** when you change architecture, mechanics, prompt
shape, or anything else documented here.

## What it is

A small open-source text MUD with a procedurally generated world. Four
AI agents (Aelinor the Scholar, Grosh the Berserker, Pippin the
Wanderer, Brother Calder the Zealot) play continuously alongside human
players in one shared world. Anonymous visitors can spectate any agent
from a sidebar; signing in by email magic link unlocks playing your own
character. Combat is turn-based 5e (d20 + stat mod + prof bonus vs AC).
NPCs follow daily routines. The DM is always reachable via `dm <msg>`,
and free-form actions get adjudicated with skill checks against your
real stats.

Local-only by default — runs entirely on Ollama, no API keys.

## Repo layout

```
nachomud/                 # the package
├── server.py             # FastAPI entrypoint: /ws, /auth/*, /privacy, /terms, /actors
├── settings.py           # env-var lookups + game tunables
├── models.py             # dataclasses: AgentState, Mob, NPC, Room, Item, ...
├── style.py              # ANSI escape constants + _c() helper
├── rules/                # game rulebook: math + race/class/level tables
│   ├── dice.py           # seedable RNG, d20 / dice notation
│   ├── stats.py          # 5e stats, point-buy, racial mods, derived values
│   ├── races.py          # RACE_DEFINITIONS
│   ├── classes.py        # CLASS_DEFINITIONS
│   └── leveling.py       # XP_TO_LEVEL, MAX_LEVEL
├── engine/               # the per-actor runtime stack
│   ├── game.py           # command dispatcher + exploration loop
│   └── session.py        # per-WS session: welcome → char_create → game
├── characters/           # everything about player characters
│   ├── character.py      # AgentState builder from class/race/stats
│   ├── creation.py       # character-creation state machine
│   ├── leveling.py       # level-up + ability unlocks
│   ├── effects.py        # StatusEffect system
│   ├── save.py           # player save/load (JSON, atomic write)
│   └── migrations.py     # schema migration framework
├── combat/
│   ├── encounter.py      # turn-based encounter state machine
│   └── abilities.py      # 24 resolvers + ABILITY_DEFINITIONS
├── ai/
│   ├── llm.py            # Ollama / Anthropic backend
│   ├── dm.py             # DM: chat + adjudication
│   ├── world_gen.py      # DM-driven procedural room generation
│   ├── npc.py            # NPC dialogue + lore summarization
│   ├── runner.py         # agent runner: per-AI async loop
│   ├── agents.py         # AGENT_DEFINITIONS for the 4 built-in personalities
│   └── contexts/         # personas / prompts (Markdown)
│       ├── _shared.md    # parent context auto-prepended to every prompt
│       ├── dm_*.md       # DM personas (persona, adjudicate, room_gen)
│       ├── npc_*.md      # NPC dialogue + summary templates
│       └── agent_*.md    # one per built-in agent
├── auth/
│   ├── magic_link.py     # token store, signed cookies, Fastmail SMTP
│   └── accounts.py       # email-keyed account files
└── world/
    ├── store.py          # rooms / mobs / items / graph / meta persistence
    ├── loop.py           # WorldLoop: shared-world owner (Actor + Subscriber + tick)
    ├── map.py            # ASCII map with per-actor fog-of-war
    ├── mobs.py           # mob mobility AI (idle/wander/pursue/return)
    ├── directions.py     # cardinal directions: VALID_DIRS, opposite(), etc.
    ├── starter.py        # loader for hand-authored starter towns
    ├── routines.py       # NPC routine projection by game-clock hour
    ├── factions.py       # faction matrix + race attitudes + aggression gating
    └── towns/            # hand-authored seed data
        └── silverbrook.json

data/                          # gitignored runtime state
├── world/<world_id>/          # rooms, mobs, items, graph, meta
├── players/<player_id>.json   # agents AND humans save here
└── accounts/<hash>.json       # email-keyed accounts
web/                           # static frontend (xterm.js, no build)
tests/                         # mirrors the package layout
```

## WorldLoop (shared world)

`world/loop.py:WorldLoop` is the single owner of the game world. One
instance per server, started by FastAPI's lifespan and torn down on
shutdown.

- **Actor registry** — 4 fixed AI agents auto-minted on first boot
  (`agent_scholar` / `agent_berserker` / `agent_wanderer` /
  `agent_zealot`) + N humans registered when WS connections enter
  in_game. Each Actor wraps an AgentState + a Game.
- **Command lock** — a `threading.Lock` serializes every actor's
  command. The async tick task acquires the same lock via
  `asyncio.to_thread`. Commands and ticks never interleave.
- **Global mob tick** — every 6 wall-seconds,
  `world/mobs.py:tick_mobs_for_rooms(active_rooms)` runs once. Returns
  witness lines keyed by room; the loop fans them onto each actor's
  pending witness queue based on which room they're standing in.
- **Subscribers** — each WS holds an `asyncio.Queue` registered as a
  Subscriber. `submit_command` and `start_actor` broadcast their msgs
  to every subscriber currently watching that actor (sync push via
  `loop.call_soon_threadsafe`). Subscribers `subscribe(actor_id)` to
  swap views; the loop sends the `subscribed` event first then replays
  the actor's transcript ring buffer (200 entries) so a swap renders
  into a cleared pane.
- **Cross-actor witness** — when an actor's `room_id` changes during a
  command, the loop queues "X heads east" / "X arrives from the south"
  lines onto every other actor in the source/destination rooms.
- **Shutdown** — cancel the tick task and the 4 agent runner tasks,
  then flush every actor's save.

## AI agents (the four personalities)

`ai/runner.py:agent_loop` is one async task per built-in agent. Each
tick: snapshot the actor's view → build a sensory user prompt → call
the LLM with the personality system prompt → parse the reply into a
single command → submit through `WorldLoop.submit_command` (echoing
the command line so spectators see what the agent decided).

Pacing: `AGENT_TICK_SECONDS = 8.0` per agent, staggered. LLM calls
happen *outside* the world lock so a slow LLM doesn't block other
actors. Dead actors skip ticks. LLM exceptions are logged and
swallowed.

Personalities load from `nachomud/ai/contexts/agent_*.md`:

- **Scholar** (Aelinor, Elf Mage) — talks, asks the DM, slow to fight
- **Berserker** (Grosh, Half-Orc Warrior) — attacks on sight, never flees
- **Wanderer** (Pippin, Halfling Ranger) — pushes into unexplored exits
- **Zealot** (Brother Calder, Human Paladin) — moralizes, fights hostile factions

All 4 contexts (and any others) inherit from `_shared.md` (world setup,
content rating 13+, voice rules) — the loader auto-prepends it.

## Auth + landing

`auth/magic_link.py` + `auth/accounts.py` + 4 routes on `server.py`.

1. **Landing page** — `web/index.html` shows a #landing div in
   the main pane (xterm hidden) when not logged in. Sidebar always
   active so anon visitors can spectate any agent.
2. **Sign in** — email entered → `POST /auth/request` → server issues a
   single-use 32-byte token (15-min TTL, in-memory, lock-guarded) and
   sends the link via Fastmail SMTP. `NACHOMUD_AUTH_DEV_ECHO=1` logs
   the link to stdout instead.
3. **Verify** — `GET /auth/verify?token=…` consumes the token, ensures
   an Account exists, sets a signed session cookie via `itsdangerous`,
   redirects to `/?auth=ok`. `Cache-Control: no-store` on the index
   page so the post-redirect JS auth check always re-runs.
4. **WS handshake** — `_resolve_player_id` reads the cookie. Auth'd →
   resolve `account.player_ids[0]` (or mint a fresh `acct-<uuid>` if
   first character). Anon → no Session, pure spectator.
5. **Routes** — `POST /auth/request`, `GET /auth/verify`,
   `POST /auth/logout`, `GET /auth/me`.

Account files live under `data/accounts/<sha256(email)>.json`.

## WebSocket protocol

```
client → server:
  {"type": "command",   "text": "look"}
  {"type": "subscribe", "actor_id": "agent_scholar"}

server → client:
  {"type": "actor_list", "actors": [...]}
  {"type": "you",        "actor_id": "human_<pid>"}
  {"type": "subscribed", "actor_id": "..."}
  {"type": "output",     "text": "...", "actor_id": "...", "ansi": true}
  {"type": "prompt",     "text": "...", "actor_id": "..."}
  {"type": "mode",       "mode": "...", "actor_id": "..."}
  {"type": "status",     "hp": ..., "actor_id": "..."}
  {"type": "thinking",   "text": "...", "actor_id": "..."}
```

`actor_id` is empty on pre-game messages (welcome / char_create) — they
go only to the producing connection.

## DM

`ai/dm.py`. Three roles, one persistent context per player:

1. **World generator** — `dm.generate_room()` runs when the player
   crosses an unexplored exit. Emits JSON for the new room.
2. **Conversation** — `dm.respond()` for chat (`dm <message>`),
   `dm.adjudicate()` for free-form actions (returns JSON: narration,
   optional skill check, optional state-changing actions, optional
   hint).
3. **Interjections** — invoked at level-up etc.

**Pending hints**: when the DM mentions a forward-looking world fact,
it can flag with `HINT: <text>`. Persisted to
`player.dm_context.pending_hints`. Future room generation respects
those hints.

## Combat (turn-based 5e)

`combat/encounter.py:Encounter` is a state machine. `attack <mob>`
triggers it; the Game routes input through `Encounter.handle_player_input`
while combat is active. Initiative is `1d20+DEX` (player wins ties).
Mob turns run synchronously via `default_mob_decider` (rule-based:
heal at 25% HP, else strongest available damage ability).

Math:
- Attack: `1d20 + STR_mod (or DEX for finesse/ranged) + prof_bonus` vs AC
- Crit: nat 20 doubles damage *dice* (not mod, 5e standard); nat 1 = miss
- Damage: weapon die + stat mod + ring/weapon bonuses
- Spells: spell attack uses `caster_mod + prof`; save DC = `8 + prof + caster_mod`

Death: 10% XP loss, full restore, teleport to `respawn_room`. Half-Orc
relentless drops to 1 HP once per long rest.

## Three time clocks

| Clock | Advances when | Frozen when |
|---|---|---|
| Wall clock | always | never |
| Game clock | actor takes an exploration action | combat active for that actor |
| Combat round | a turn resolves | not in combat |

Game-clock cost: move +1m, look/talk/dm +5m, wait/sleep variable.
Mob ticking is now driven by WorldLoop, not per-command.

## Classes + races

| Class | Hit die | Primary | Caster | Starting | Unlocks |
|---|---|---|---|---|---|
| Warrior | d10 | STR | — | attack, defend | taunt@L3, cleave@L5, rally@L7 |
| Paladin | d8 | STR | CHA | attack, shield | smite@L3, lay_on_hands@L5, consecrate@L7 |
| Mage | d4 | INT | INT | attack, missile | barrier@L3, curse@L5, arcane_storm@L7 |
| Cleric | d8 | WIS | WIS | attack, heal | ward@L3, holy_bolt@L5, cure@L7 |
| Ranger | d8 | DEX | WIS | attack, aimed_shot | poison_arrow@L3, volley@L5, sleep@L7 |
| Rogue | d6 | DEX | — | attack, backstab | evade@L3, bleed@L5, smoke_bomb@L7 |

Races: Human (+1 all), Dwarf (+2 CON +1 STR), Elf (+2 DEX +1 INT),
Halfling (+2 DEX +1 CHA), Half-Orc (+2 STR +1 CON, relentless).

## Environment vars

- `LLM_BACKEND` — `ollama` (default) or `anthropic`
- `LLM_SMART_MODEL` — DM, NPC dialogue (default `llama3.1:8b-instruct-q4_K_M`)
- `LLM_FAST_MODEL` — agent runner (default `llama3.2:3b`)
- `OLLAMA_BASE_URL` — default `http://localhost:11434`
- `NACHOMUD_DATA_ROOT` / `NACHOMUD_PLAYERS_ROOT` / `NACHOMUD_ACCOUNTS_ROOT`
  — override save dirs (used by tests)
- `NACHOMUD_SECRET_KEY` — signing key for session cookies; **must be
  set in production** (random 32+ bytes). In dev a fresh ephemeral key
  is generated each restart.
- `NACHOMUD_AUTH_DEV_ECHO=1` — log magic links to stdout instead of
  emailing
- `NACHOMUD_SMTP_HOST` / `_PORT` / `_USER` / `_PASSWORD` — outbound
  SMTP for magic-link email (default `smtp.fastmail.com:465`)
- `NACHOMUD_MAIL_FROM` — From: address
- `NACHOMUD_SECURE_COOKIE=1` — set the Secure flag on the session
  cookie (required in production / HTTPS)
- `NACHOMUD_DISABLE_AGENTS=1` — skip spawning the 4 LLM agent runners
  (set by tests so Ollama isn't required)
- `NACHOMUD_AGENT_LLM_TIMEOUT` — seconds an agent waits for the LLM
  before skipping a tick (default 30). Hard ceiling that prevents a
  wedged Ollama from parking the agent loop forever.

## Run + test

```bash
./run.sh                  # uvicorn nachomud.server:app on :4000
pytest tests/             # all tests
pytest tests/world/       # one subdir
NACHOMUD_AUTH_DEV_ECHO=1 ./run.sh   # local dev: log magic links instead of emailing
```

LLM calls in tests are mocked with `lambda s, u: "..."`. Dice are
seeded with `dice.seed(0xDEADBEEF)`. Agent runner is disabled via
`NACHOMUD_DISABLE_AGENTS=1`.

## Common contribution tasks

- **New race** → `RACE_DEFINITIONS` in `nachomud/rules/`
- **New class** → `CLASS_DEFINITIONS` in `nachomud/rules/` + ability
  resolvers in `nachomud/combat/abilities.py`
- **New ability** → `ABILITY_DEFINITIONS` in `nachomud/rules/`,
  register resolver in `ABILITY_REGISTRY`
- **New starter town** → drop JSON in `nachomud/world/towns/`, call
  `nachomud.world.starter.seed_world(world_id, town=name)`
- **Tune mob mobility** → `P_*` constants at top of `nachomud/world/mobs.py`
- **Tune DM persona** → `DM_PERSONA` / `ADJUDICATE_PERSONA` in
  `nachomud/ai/dm.py` (or extract to `nachomud/ai/contexts/*.md`)
- **Tune agent personalities** → edit `nachomud/ai/contexts/agent_*.md`
  (no code change needed)

## DM conjuring rules

| | Allowed | Forbidden |
|---|---|---|
| Conjure | Plausible NPCs/buildings/exits in the right zone | Quest McGuffins, arbitrary gold piles, instant-escape exits |
| Adjust | Drop a healing potion if HP critical near a fight; clue if stuck | Resurrect; skip a fight you started |
| Adjudicate | DCs and skill checks against player's real stats | Auto-success / auto-fail punitively |
| Retcon | Never | All retcons (rooms are frozen) |
| Tone | DM voice, ground in seen world | Meta references, breaking character |
