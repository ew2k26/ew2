#!/usr/bin/env python3
"""Klatom – Test Mode (token management, proxy speed, auth tools)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent

DATA = ROOT / "data"
AUTH_FILE = DATA / ".auth"
SESSION_FILE = DATA / ".session"
TOKENS_FILE = DATA / ".tokens"
RESULTS_DIR = ROOT / "results"


class C:
    PRIMARY = "#A855F7"
    SUCCESS = "#30D158"
    DANGER = "#FF453A"
    WARNING = "#FF9F0A"
    MUTED = "#7A7A82"

VERSION = "3.3.0"


console = Console()


def _hwid() -> str:
    try:
        parts = [platform.node(), platform.machine(), platform.processor(), str(uuid.getnode())]
        for cmd, field in [
            (["wmic", "baseboard", "get", "serialnumber"], "SerialNumber"),
            (["wmic", "diskdrive", "get", "serialnumber"], "SerialNumber"),
        ]:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                for line in r.stdout.splitlines():
                    s = line.strip()
                    if s and s != field:
                        parts.append(s)
                        break
            except Exception:
                pass
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]
    except Exception:
        return "unknown"


def _banner():
    from rich.text import Text
    from rich import box
    inner = Text()
    inner.append("  ██╗  ██╗██╗      █████╗ ███╗   ██╗████████╗ ██████╗ ███╗   ███╗", style=f"bold {C.PRIMARY}")
    inner.append("\n  ██║ ██╔╝██║     ██╔══██╗████╗  ██║╚══██╔══╝██╔═══██╗████╗ ████║", style=f"bold {C.PRIMARY}")
    inner.append("\n  █████╔╝ ██║     ███████║██╔██╗ ██║   ██║   ██║   ██║██╔████╔██║", style=f"bold {C.PRIMARY}")
    inner.append("\n  ██╔═██╗ ██║     ██╔══██║██║╚██╗██║   ██║   ██║   ██║██║╚██╔╝██║", style=f"bold {C.PRIMARY}")
    inner.append("\n  ██║  ██╗███████╗██║  ██║██║ ╚████║   ██║   ╚██████╔╝██║ ╚═╝ ██║", style=f"bold {C.PRIMARY}")
    inner.append("\n  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝", style=f"bold {C.PRIMARY}")
    inner.append(f"\n\n  [bold {C.WARNING}]MOD PANEL[/]", style=f"{C.WARNING}")
    inner.append(f"\n         v{VERSION}", style=f"{C.MUTED}")
    return Panel(inner, box=box.DOUBLE, border_style=C.WARNING, padding=(0, 1))


def _show_session():
    hwid = _hwid()
    auth_data = None
    if AUTH_FILE.exists():
        try:
            from crypto import load_auth
            auth_data = load_auth(AUTH_FILE)
        except Exception:
            pass
    session_data = None
    if SESSION_FILE.exists():
        try:
            from crypto import load_session
            session_data = load_session(SESSION_FILE)
        except Exception:
            pass
    tokens_count = 0
    if TOKENS_FILE.exists():
        try:
            tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
            tokens_count = len(tokens)
        except Exception:
            pass

    hits_count = 0
    hits_file = RESULTS_DIR / "hits.txt"
    if hits_file.exists():
        hits_count = len([l for l in hits_file.read_text(encoding="utf-8").splitlines() if l.strip()])

    t = Table(box=None, show_header=False, padding=(0, 2))
    t.add_column(style=C.MUTED, width=16)
    t.add_column(style="white")
    t.add_row("HWID", f"[{C.MUTED}]{hwid}[/]")
    t.add_row("Machine", f"[{C.MUTED}]{platform.node()}[/]")

    if auth_data:
        token_hashes = auth_data.get("t", [])
        t.add_row("Stored Tokens", f"[{C.PRIMARY}]{len(token_hashes)}[/] (hashed)")
    else:
        t.add_row("Auth File", f"[{C.DANGER}]Not found[/]")

    if session_data:
        start = session_data.get("ts", 0)
        if start:
            remaining = max(0, 86400 - (time.time() - start))
            if remaining > 0:
                h = int(remaining // 3600)
                m = int((remaining % 3600) // 60)
                s = int(remaining % 60)
                color = C.SUCCESS if remaining > 3600 else C.WARNING
                t.add_row("Trial Status", f"[{color}]ACTIVE[/]")
                t.add_row("Time Left", f"[{color}]{h}h {m}m {s}s[/]")
                expires = datetime.now() + timedelta(seconds=remaining)
                t.add_row("Expires", f"[{C.MUTED}]{expires.strftime('%Y-%m-%d %H:%M')}[/]")
            else:
                t.add_row("Trial Status", f"[{C.DANGER}]EXPIRED[/]")
        else:
            t.add_row("Trial Status", f"[{C.DANGER}]Not started[/]")
    else:
        t.add_row("Trial Status", f"[{C.DANGER}]No session[/]")

    t.add_row("Tokens File", f"[{C.PRIMARY}]{tokens_count}[/] tokens")
    t.add_row("Hits Found", f"[{C.SUCCESS}]{hits_count}[/]")

    console.print()
    console.print(Panel(
        t, title=f"[{C.WARNING}]Session Info — TEST MODE[/]",
        title_align="left", border_style=C.WARNING, padding=(0, 1),
    ))


def _generate_tokens():
    from crypto import generate_token as _gen
    count = IntPrompt.ask("How many tokens to generate", default=1)
    if count < 1:
        count = 1
    tokens = []
    if TOKENS_FILE.exists():
        try:
            tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
        except Exception:
            tokens = []
    new_tokens = []
    for _ in range(count):
        tok = _gen()
        new_tokens.append(tok)
        tokens.append(tok)
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    console.print(f"\n[{C.SUCCESS}]Generated {count} token(s):[/]")
    for t in new_tokens:
        console.print(f"  [{C.PRIMARY}]{t}[/]")
    console.print(f"  [{C.MUTED}]Total: {len(tokens)}[/]\n")


def _list_tokens():
    if not TOKENS_FILE.exists():
        console.print(f"\n[{C.DANGER}]No tokens file found.[/]\n")
        return
    try:
        tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    except Exception:
        console.print(f"\n[{C.DANGER}]Invalid tokens file.[/]\n")
        return
    if not tokens:
        console.print(f"\n[{C.MUTED}]No tokens stored.[/]\n")
        return
    console.print(f"\n[{C.PRIMARY}]Stored Tokens ({len(tokens)}):[/]")
    for i, t in enumerate(tokens, 1):
        console.print(f"  [{C.MUTED}]{i}.[/] [{C.PRIMARY}]{t}[/]")
    console.print()


def _revoke_token():
    if not TOKENS_FILE.exists():
        console.print(f"\n[{C.DANGER}]No tokens file found.[/]\n")
        return
    try:
        tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    except Exception:
        console.print(f"\n[{C.DANGER}]Invalid tokens file.[/]\n")
        return
    _list_tokens()
    token = Prompt.ask("Token to revoke").strip()
    if token in tokens:
        tokens.remove(token)
        TOKENS_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
        console.print(f"\n[{C.SUCCESS}]Revoked. Total: {len(tokens)}[/]\n")
    else:
        console.print(f"\n[{C.DANGER}]Token not found.[/]\n")


def _reset_trial():
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
        console.print(f"\n[{C.SUCCESS}]Trial session deleted.[/]\n")
    else:
        console.print(f"\n[{C.MUTED}]No session to delete.[/]\n")
    if Confirm.ask("Start a new 24h trial now?"):
        from crypto import save_session, get_hwid
        save_session(SESSION_FILE, time.time(), get_hwid())
        console.print(f"\n[{C.SUCCESS}]New trial activated — 24h started.[/]\n")


def _add_token():
    token = Prompt.ask("Token to approve").strip()
    if not token:
        console.print(f"\n[{C.DANGER}]No token entered.[/]\n")
        return
    from auth import add_approved_token
    add_approved_token(token)
    console.print(f"\n[{C.SUCCESS}]Token approved: {token}[/]\n")


def _view_hits():
    hits_file = RESULTS_DIR / "hits.txt"
    if not hits_file.exists():
        console.print(f"\n[{C.DANGER}]No hits file found.[/]\n")
        return
    hits = [l.strip() for l in hits_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not hits:
        console.print(f"\n[{C.MUTED}]No hits yet.[/]\n")
        return
    console.print(f"\n[{C.SUCCESS}]Available usernames ({len(hits)}):[/]")
    for i, h in enumerate(hits[:50], 1):
        console.print(f"  [{C.MUTED}]{i}.[/] [{C.SUCCESS}]{h}[/]")
    if len(hits) > 50:
        console.print(f"  [{C.MUTED}]...and {len(hits) - 50} more[/]")
    console.print()


def _clear_auth():
    console.print(f"\n[{C.WARNING}]This will delete ALL auth data.[/]")
    if not Confirm.ask("Are you sure?", default=False):
        return
    for f in [AUTH_FILE, SESSION_FILE]:
        if f.exists():
            f.unlink()
    if TOKENS_FILE.exists():
        TOKENS_FILE.write_text("[]", encoding="utf-8")
    console.print(f"\n[{C.SUCCESS}]All auth data cleared.[/]\n")


def _check_updates():
    import asyncio
    from github_loader import decrypt_url

    url = decrypt_url()
    if not url:
        console.print(f"\n[{C.DANGER}]Could not decrypt GitHub URL.[/]\n")
        return

    console.print(f"\n[{C.MUTED}]Checking GitHub for updates...[/]")

    async def _check():
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(f"{url}/config.json", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        remote_ver = data.get("version", "unknown")
                        console.print(f"  [{C.SUCCESS}]Remote version: {remote_ver}[/]")
                        console.print(f"  [{C.MUTED}]Local version:  2.1.1[/]")
                    else:
                        console.print(f"  [{C.DANGER}]Failed to fetch config (HTTP {resp.status})[/]")
        except Exception as e:
            console.print(f"  [{C.DANGER}]Error: {e}[/]")
        console.print()

    asyncio.run(_check())


def main():
    try:
        from mod_gui import main as gui_main
        gui_main()
    except Exception:
        # Fallback to terminal
        _terminal_main()


def _terminal_main():
    console.clear()
    console.print(_banner())
    _show_session()

    while True:
        console.print(f"\n[{C.PRIMARY}]Test Menu:[/]")
        console.print(f"  [{C.PRIMARY}]1[/] Show session info")
        console.print(f"  [{C.PRIMARY}]2[/] Generate tokens")
        console.print(f"  [{C.PRIMARY}]3[/] List tokens")
        console.print(f"  [{C.PRIMARY}]4[/] Revoke token")
        console.print(f"  [{C.PRIMARY}]5[/] Add approved token")
        console.print(f"  [{C.PRIMARY}]6[/] Reset/start trial")
        console.print(f"  [{C.PRIMARY}]7[/] Test proxy speed")
        console.print(f"  [{C.PRIMARY}]8[/] View hits")
        console.print(f"  [{C.PRIMARY}]9[/] Check updates")
        console.print(f"  [{C.PRIMARY}]10[/] Clear all auth")
        console.print(f"  [{C.PRIMARY}]11[/] Exit")
        choice = Prompt.ask(f"\n[{C.PRIMARY}]Choice[/]", default="1").strip()
        if choice == "1":
            _show_session()
        elif choice == "2":
            _generate_tokens()
        elif choice == "3":
            _list_tokens()
        elif choice == "4":
            _revoke_token()
        elif choice == "5":
            _add_token()
        elif choice == "6":
            _reset_trial()
        elif choice == "7":
            asyncio.run(_test_proxy_speed())
        elif choice == "8":
            _view_hits()
        elif choice == "9":
            _check_updates()
        elif choice == "10":
            _clear_auth()
        elif choice == "11":
            break
        else:
            console.print(f"[{C.DANGER}]Invalid option.[/]")


async def _test_proxy_speed():
    from config import ENDPOINT
    proxy_file = DATA / "proxies.txt"
    if not proxy_file.exists():
        console.print(f"\n[{C.DANGER}]No proxies.txt found in data/[/]\n")
        return
    proxies = [p.strip() for p in proxy_file.read_text(encoding="utf-8").splitlines() if p.strip()]
    if not proxies:
        console.print(f"\n[{C.DANGER}]No proxies in file.[/]\n")
        return

    console.print(f"\n[{C.MUTED}]Testing {len(proxies)} proxies...[/]")
    sem = asyncio.Semaphore(200)
    results = []
    tested = 0
    lock = asyncio.Lock()

    async def _test_one(sess, proxy_raw):
        nonlocal tested
        async with sem:
            proxy = proxy_raw.strip()
            if not proxy.startswith("http"):
                proxy = f"http://{proxy}"
            try:
                start = time.time()
                async with sess.post(
                    ENDPOINT, json={"username": "a"}, proxy=proxy,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status in (200, 201, 204, 400, 429):
                        latency = time.time() - start
                        async with lock:
                            results.append((proxy_raw, latency, resp.status))
            except Exception:
                pass
            async with lock:
                tested += 1
            if tested % 100 == 0 or tested == len(proxies):
                console.print(f"  [{C.MUTED}]{tested}/{len(proxies)}[/]")

    connector = aiohttp.TCPConnector(limit=200, limit_per_host=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(
        connector=connector, timeout=aiohttp.ClientTimeout(total=5), trust_env=False,
    ) as sess:
        tasks = [_test_one(sess, p) for p in proxies]
        await asyncio.gather(*tasks)

    if not results:
        console.print(f"\n[{C.DANGER}]No working proxies found.[/]\n")
        return

    results.sort(key=lambda x: x[1])
    t = Table(box=None, show_header=True, padding=(0, 1))
    t.add_column("#", style=C.MUTED, width=4)
    t.add_column("Proxy", style="white")
    t.add_column("Latency", style=C.SUCCESS, width=10)
    t.add_column("Status", width=8)
    for i, (proxy, lat, status) in enumerate(results[:20], 1):
        color = C.SUCCESS if lat < 1 else C.WARNING if lat < 3 else C.DANGER
        t.add_row(str(i), proxy, f"{lat:.2f}s", f"[{color}]{status}[/]")
    console.print()
    console.print(Panel(
        t, title=f"[{C.PRIMARY}]Proxy Speed Results[/] — {len(results)}/{len(proxies)} alive",
        title_align="left", border_style=C.PRIMARY,
    ))
    fast = [p for p, _, _ in results]
    fast_file = DATA / "proxies_fast.txt"
    fast_file.write_text("\n".join(fast), encoding="utf-8")
    console.print(f"\n[{C.SUCCESS}]Saved {len(fast)} working proxies to data/proxies_fast.txt[/]\n")


if __name__ == "__main__":
    main()
