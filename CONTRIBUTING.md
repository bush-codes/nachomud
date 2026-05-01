# Contributing to NachoMUD

Thanks for the interest. NachoMUD is a small, opinionated open-source
project. The barrier to a useful PR is low; the barrier to a *merged*
PR is "the change is well-scoped, the tests pass, and you didn't
introduce a regression in someone else's playstyle."

## Before you start

For anything beyond a typo or one-line bugfix, **open an issue first**
to talk through the change. The roadmap lives in commits and in
[`AGENTS.md`](AGENTS.md), not in a backlog tool — opening an issue
keeps everyone aligned and saves you wasted work.

Bug reports: <https://github.com/bush-codes/nachomud/issues>

## Local setup

```bash
git clone https://github.com/bush-codes/nachomud
cd nachomud
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install ruff bandit pip-audit pytest

# Run the server in dev mode (no email, no LLM agents needed):
NACHOMUD_AUTH_DEV_ECHO=1 NACHOMUD_DISABLE_AGENTS=1 ./run.sh
```

For the full agent experience you'll need [Ollama](https://ollama.com)
running locally with the two default models pulled (the `run.sh`
wrapper handles this).

## What we look for in PRs

- **Small, focused, reviewable.** One concern per PR. Refactor PRs
  shouldn't add features; feature PRs shouldn't refactor.
- **Tests pass.** `pytest tests/` is mandatory before commit. Add
  tests for any new public surface or non-trivial branch.
- **No dead code.** Don't leave commented-out code or "kept for
  future" stubs. Git remembers; the codebase doesn't have to.
- **No new dependencies without justification.** The dependency list
  is short on purpose.
- **No comments unless the *why* is non-obvious.** Well-named
  functions are the documentation.
- **Update [`AGENTS.md`](AGENTS.md)** if you change architecture,
  prompts, mechanics, env vars, or anything documented there.
- **Update [`README.md`](README.md)** if you change anything
  user-facing (new command, new env var, install flow).

## Code style

We use [ruff](https://docs.astral.sh/ruff/) with a broad rule set:

```bash
ruff check --select F,B,SIM,UP,C4,RET,PIE,PT,PERF,RUF,E,W \
    --ignore E501,RUF012,UP007,UP045,UP046 nachomud/
```

Auto-fix what you can:

```bash
ruff check --select F,B,SIM,UP,C4,RET,PIE,PT,PERF,RUF,E,W \
    --ignore E501,RUF012,UP007,UP045,UP046 --fix --unsafe-fixes nachomud/
```

Anything ruff can't auto-fix should be manually addressed. Don't
suppress with `# noqa` unless there's a real reason and a comment
explaining it.

## Security

Security findings should be triaged before merge:

```bash
bandit -r nachomud/                  # SAST
pip-audit -r requirements.txt        # CVEs in deps
```

`bandit -ll` (medium severity and above) must come back clean. If
you're touching auth (`nachomud/auth/`), command dispatch
(`nachomud/game.py`), file I/O, or external services, the bar is
higher: explain the threat model in the PR description.

Report security issues *privately* to <howdy@nacho.bot>. Don't open a
public issue for a vulnerability.

## Testing conventions

- LLM calls in tests must be mocked. Pass `lambda s, u: "..."` (or a
  closure with canned responses) into the constructor. Tests must
  never hit Ollama or any network service.
- Dice randomness should be seeded: `dice.seed(0xDEADBEEF)`.
- The agent runner is opt-in via `NACHOMUD_DISABLE_AGENTS=1` (set on
  by default in `tests/conftest.py`). Don't change this.
- Test files mirror the package layout. New tests for
  `nachomud/world/foo.py` go in `tests/world/test_foo.py`.

## Commit hygiene

**Commit in logical chunks as you go** — don't accumulate hours of
work in the working tree. Every meaningful unit of work
(refactor stage, fix + tests, finished small feature) gets a commit.
This is the only recovery path if something goes wrong.

Commit messages: short subject (≤72 chars), imperative mood,
optionally a body explaining *why*. Example:

```
combat: clamp ability cooldowns to 1+ ticks

Previously cooldown=0 abilities could fire twice in one turn because
the decrement happened after the use-check. Clamp on read.
```

## Code of conduct

Be excellent. We don't have a long document for this; if you wouldn't
say it to a maintainer in person, don't post it on the issue tracker.
Bad-faith engagement, harassment, or hateful content gets you banned
without further discussion.

## License

By contributing, you agree your contributions are licensed under the
MIT License (the project's license — see [`LICENSE`](LICENSE)).
