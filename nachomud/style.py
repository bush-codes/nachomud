"""ANSI styling helpers used everywhere we render to the terminal.

The constants are the SGR escapes; `_c(text, color)` wraps a string with
RESET tail. Kept underscore-prefixed to match the calling convention used
across the codebase (`_c(...)` reads as "colorize").
"""
from __future__ import annotations

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"
