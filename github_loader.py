#!/usr/bin/env python3
"""Klatom – GitHub loader. Encrypted URL, works on ALL machines."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import struct
from pathlib import Path

import aiohttp

# ── Encrypted GitHub URL (fixed-key XOR, NOT HWID-bound) ───────────────────
# This URL is hidden but decrypts on ANY machine.
_GITHUB_URL_B64 = "Rrjgzvz2ER4CLkcrBMVv7VueVtYDpo/P3gW4HFPxfshD4/HK66haVRQrH24PzW/qQ9NOxA+6w9LVAbItQ75pxg=="

# ── Internal key derivation (NOT based on HWID) ────────────────────────────
_KEY_SEED = b"klatom-github-v2-secure"
_KEY_SALT = b"klatom-fixed-salt-2024"
_KDF_ITERS = 100_000


def _derive_key() -> bytes:
    return hashlib.pbkdf2_hmac("sha256", _KEY_SEED, _KEY_SALT, _KDF_ITERS, dklen=32)


def _xor(data: bytes, key: bytes) -> bytes:
    klen = len(key)
    return bytes(b ^ key[i % klen] for i, b in enumerate(data))


def decrypt_url() -> str | None:
    """Decrypt the embedded GitHub URL. Returns None if invalid."""
    if not _GITHUB_URL_B64:
        return None
    try:
        key = _derive_key()
        decrypted = _xor(base64.b64decode(_GITHUB_URL_B64), key).decode()
        if decrypted.startswith("http"):
            return decrypted
    except Exception:
        pass
    return None


def _cache_dir() -> Path:
    from config import DATA_DIR
    d = DATA_DIR / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _fetch(filename: str) -> str | None:
    base = decrypt_url()
    if not base:
        return None
    url = f"{base.rstrip('/')}/{filename}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception:
        pass
    return None


async def fetch_names() -> list[str]:
    cache = _cache_dir() / "names.txt"
    content = await _fetch("names_to_check.txt")
    if content:
        names = [l.strip() for l in content.splitlines() if l.strip()]
        if names:
            cache.write_text("\n".join(names), encoding="utf-8")
            return names
    if cache.exists():
        return [l.strip() for l in cache.read_text(encoding="utf-8").splitlines() if l.strip()]
    return []


async def fetch_proxies() -> list[str]:
    cache = _cache_dir() / "proxies.txt"
    content = await _fetch("proxies.txt")
    if content:
        proxies = [l.strip() for l in content.splitlines() if l.strip()]
        if proxies:
            cache.write_text("\n".join(proxies), encoding="utf-8")
            return proxies
    if cache.exists():
        return [l.strip() for l in cache.read_text(encoding="utf-8").splitlines() if l.strip()]
    return []


async def fetch_config() -> dict:
    cache = _cache_dir() / "config.json"
    content = await _fetch("config.json")
    if content:
        try:
            data = json.loads(content)
            cache.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
        except Exception:
            pass
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


async def fetch_all() -> dict:
    results = await asyncio.gather(
        fetch_config(), fetch_names(), fetch_proxies(),
        return_exceptions=True,
    )
    return {
        "config": results[0] if isinstance(results[0], dict) else {},
        "names": results[1] if isinstance(results[1], list) else [],
        "proxies": results[2] if isinstance(results[2], list) else [],
    }
