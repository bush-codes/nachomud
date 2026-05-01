"""Per-email account storage.

Each account file is `data/accounts/<sha256(lowercased_email)>.json` and
holds:
  - the canonical email
  - created_at
  - the list of player_ids this account owns

Filenames are hashed so listing the directory doesn't leak email
addresses; we never need to list anyway. Lookups go through
`find_account_by_email`.

Linked players: an account may "claim" anonymous saves by appending the
anon player_id to its `player_ids` list. The actual character JSON
stays in `data/players/<player_id>.json` — accounts only hold pointers.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Optional


SCHEMA_VERSION_ACCOUNT = 1

DATA_ROOT = os.environ.get(
    "NACHOMUD_ACCOUNTS_ROOT",
    os.path.join("data", "accounts"),
)


@dataclass
class Account:
    email: str
    created_at: float = field(default_factory=time.time)
    player_ids: list[str] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION_ACCOUNT


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _account_path(email: str) -> str:
    return os.path.join(DATA_ROOT, f"{_email_hash(email)}.json")


def _ensure_root() -> None:
    os.makedirs(DATA_ROOT, exist_ok=True)


def _atomic_write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
    os.replace(tmp, path)


def find_account_by_email(email: str) -> Optional[Account]:
    path = _account_path(email)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            d = json.load(f)
        return Account(
            email=d["email"],
            created_at=float(d.get("created_at", time.time())),
            player_ids=list(d.get("player_ids", [])),
            schema_version=int(d.get("schema_version", 1)),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def create_account(email: str) -> Account:
    """Create a new account for `email`. Idempotent — if one already
    exists, returns it unchanged. Email is canonicalized to lowercase."""
    existing = find_account_by_email(email)
    if existing is not None:
        return existing
    _ensure_root()
    account = Account(email=email.strip().lower())
    save_account(account)
    return account


def save_account(account: Account) -> None:
    _ensure_root()
    _atomic_write_json(_account_path(account.email), asdict(account))


def link_player(account: Account, player_id: str) -> Account:
    """Add `player_id` to the account's player list (deduped). Persists.
    Returns the updated Account."""
    if player_id and player_id not in account.player_ids:
        account.player_ids.append(player_id)
        save_account(account)
    return account


def primary_player_id(account: Account) -> str:
    return account.player_ids[0] if account.player_ids else ""
