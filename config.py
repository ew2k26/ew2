#!/usr/bin/env python3
"""KLATOM v3.2 - Configuration, constants, helpers, and data models."""

from __future__ import annotations

import json
import string
import sys
from dataclasses import dataclass, field
from pathlib import Path

if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent

APPDATA_DIR = Path.home() / "AppData" / "Local" / "Klatom"
DATA_DIR = APPDATA_DIR / "data"
LOGS_DIR = APPDATA_DIR / "logs"
RESULTS_DIR = APPDATA_DIR / "results"

VERSION = "3.3.0"
ENDPOINT = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"
USERNAME_CHARS = string.ascii_lowercase + string.digits + "_" + "."
MAX_CONCURRENCY = 2000


class C:
    PRIMARY   = "#A855F7"
    PRIMARY_D = "#7C3AED"
    SUCCESS   = "#30D158"
    DANGER    = "#FF453A"
    WARNING   = "#FF9F0A"
    MUTED     = "#7A7A82"
    BORDER    = "#3A3A42"
    BG        = "#1A1A22"


def ensure_dir(*paths: str | Path) -> None:
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)


def ensure_file(filepath: str | Path, *, clean: bool = False) -> None:
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    if clean or not path.exists():
        path.write_text("", encoding="utf-8")


def load_lines(filepath: str | Path) -> list[str]:
    path = Path(filepath)
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def is_valid_username(name: str) -> bool:
    if not (2 <= len(name) <= 32):
        return False
    if ".." in name:
        return False
    if name.startswith(".") or name.endswith("."):
        return False
    return all(c in USERNAME_CHARS for c in name)


class Config:
    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else DATA_DIR / "config.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists() and self._path.stat().st_size > 0:
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}
        else:
            self._path.write_text("{}", encoding="utf-8")

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get_masked(self, key: str, default=None) -> str:
        val = self._data.get(key, default)
        if not val or not isinstance(val, str):
            return val
        if "webhook" in key.lower() or "discord.com/api/webhooks" in val:
            parts = val.rsplit("/", 1)
            if len(parts) == 2 and len(parts[1]) > 8:
                return parts[0] + "/" + "\u2022" * (len(parts[1]) - 8) + parts[1][-8:]
        return val

    def get_all(self) -> dict:
        return dict(self._data)


@dataclass
class AppSettings:
    debug: bool = False
    verbose: bool = False
    no_wizard: bool = False
    mod: bool = False
    terminal: bool = False


@dataclass
class RunConfig:
    proxies: list[str]
    remove_bad_proxies: bool
    usernames: list[str]
    concurrency: int
    timeout: int
    scraped: bool = False
    webhook_url: str | None = None
    webhook_message: str | None = None


@dataclass
class Stats:
    requests: int = 0
    works: int = 0
    taken: int = 0
    ratelimited: int = 0
    errors: int = 0
    circuit_opens: int = 0
    rps: float = 0.0
    checks_rps: float = 0.0
    peak_rps: float = 0.0
    best_streak: int = 0
    _streak: int = 0
    _lock: field(default_factory=lambda: __import__("asyncio").Lock) = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        import asyncio
        self._lock = asyncio.Lock()

    async def inc_requests(self) -> None:
        async with self._lock:
            self.requests += 1

    async def inc_works(self) -> None:
        async with self._lock:
            self.works += 1
            self._streak += 1
            if self._streak > self.best_streak:
                self.best_streak = self._streak

    async def inc_taken(self) -> None:
        async with self._lock:
            self.taken += 1
            self._streak = 0

    async def inc_ratelimited(self) -> None:
        async with self._lock:
            self.ratelimited += 1

    async def inc_errors(self) -> None:
        async with self._lock:
            self.errors += 1

    async def inc_circuit_open(self) -> None:
        async with self._lock:
            self.circuit_opens += 1

    async def set_rps(self, value: float) -> None:
        async with self._lock:
            self.rps = value
            if value > self.peak_rps:
                self.peak_rps = value

    async def set_checks_rps(self, value: float) -> None:
        async with self._lock:
            self.checks_rps = value

    async def snapshot(self) -> dict:
        async with self._lock:
            return {
                "requests": self.requests,
                "works": self.works,
                "taken": self.taken,
                "ratelimited": self.ratelimited,
                "errors": self.errors,
                "circuit_opens": self.circuit_opens,
                "rps": self.rps,
                "checks_rps": self.checks_rps,
                "peak_rps": self.peak_rps,
                "best_streak": self.best_streak,
            }
