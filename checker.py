#!/usr/bin/env python3
"""Klatom v3.0.0 - Discord username checker."""
from __future__ import annotations

import sys, os, logging, warnings, asyncio

for _n in ("aiohttp", "aiohttp.client", "aiohttp.access", "aiohttp.internal"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", message=".*[Uu]nclosed.*")
warnings.filterwarnings("ignore", message=".*[Cc]onnection.*")

try:
    import asyncio.sslproto as _sslproto
    _orig_eof = _sslproto.SSLProtocol.eof_received
    def _safe_eof(self):
        try:
            return _orig_eof(self)
        except RuntimeError:
            return False
    _sslproto.SSLProtocol.eof_received = _safe_eof
except Exception:
    pass

try:
    import asyncio.proactor_events as _proactor
    _orig_cl = _proactor._ProactorBasePipeTransport._call_connection_lost
    def _silent_cl(self, exc):
        try:
            _orig_cl(self, exc)
        except ConnectionResetError:
            pass
    _proactor._ProactorBasePipeTransport._call_connection_lost = _silent_cl
except Exception:
    pass

import ctypes
try:
    k = ctypes.windll.kernel32
    u = ctypes.windll.user32
    h = k.GetConsoleWindow()
    if h:
        u.SetWindowTextW(h, "Klatom v3.0.0 - Discord Username Checker")
except Exception:
    pass

import argparse, asyncio, random, sys, time
from pathlib import Path

from config import (
    DATA_DIR, LOGS_DIR, MAX_CONCURRENCY, RESULTS_DIR, CHECKED_FILE,
    AppSettings, Config, RunConfig, Stats, ensure_dir, ensure_file, load_lines, C,
)
from ui import (
    banner, card, console, config_summary, fail, final_summary, info, ok,
    progress_steps, section, warn_card,
)
from engine import Checker
from wizard import setup_wizard
from auth import check_auth, show_session_info


def main():
    parser = argparse.ArgumentParser(description="Klatom")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-wizard", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    settings = AppSettings(debug=args.debug, no_wizard=args.no_wizard,
                           resume=args.resume, clear=args.clear)
    config = Config()

    if settings.clear:
        for f in [CHECKED_FILE, RESULTS_DIR / "hits.txt", RESULTS_DIR / "takens.txt"]:
            if f.exists():
                f.unlink()
        ok("Cleared results")
        return

    asyncio.run(_run(settings, config))


async def _run(settings: AppSettings, config: Config) -> None:
    console.clear()
    console.print(banner())
    console.print()

    webhook_url = config.get("webhook", "")

    authorized, token = await check_auth(webhook_url)
    if not authorized:
        return

    if settings.no_wizard:
        run_config = _load_saved_config(config)
        if not run_config:
            fail("No saved config. Run without --no-wizard first.")
            return
    else:
        run_config = await setup_wizard(config, settings)
        config.set("last_proxies", run_config.proxies)
        config.set("last_concurrency", run_config.concurrency)
        config.set("last_timeout", run_config.timeout)

    if not run_config.usernames:
        fail("No usernames to check!")
        return

    await _run_checker(run_config, settings)


def _load_saved_config(config: Config) -> RunConfig | None:
    proxies = config.get("last_proxies", [])
    concurrency = config.get("last_concurrency", 50)
    timeout = config.get("last_timeout", 5)
    names_file = config.get("last_names_file", str(DATA_DIR / "names.txt"))
    names = load_lines(names_file)
    if not names:
        return None
    return RunConfig(
        proxies=proxies, remove_bad=True, usernames=names,
        concurrency=concurrency, timeout=timeout,
        webhook_url=config.get("webhook"),
        webhook_msg=config.get("webhook_message"),
    )


async def _run_checker(cfg: RunConfig, settings: AppSettings) -> None:
    ensure_dir(RESULTS_DIR)
    _hits_path = RESULTS_DIR / "hits.txt"
    _taken_path = RESULTS_DIR / "takens.txt"
    _hits_file = _hits_path.open("a", encoding="utf-8")
    _taken_file = _taken_path.open("a", encoding="utf-8")

    checked_names: set[str] = set()
    if settings.resume and CHECKED_FILE.exists():
        checked_names = set(load_lines(CHECKED_FILE))
        info(f"Resumed with {len(checked_names)} checked")

    remaining = [u for u in cfg.usernames if u not in checked_names]
    if not remaining:
        ok("All usernames already checked!")
        return

    random.shuffle(remaining)

    stats = Stats()
    checker = Checker(cfg, stats, cfg.webhook_url or "",
                      cfg.webhook_msg or "**<name>** available | <t:time:R>")
    await checker.start()

    _checked_file = CHECKED_FILE.open("a", encoding="utf-8")
    _checked_lock = asyncio.Lock()
    _hits_lock = asyncio.Lock()
    _taken_lock = asyncio.Lock()
    _rate_count = 0

    sem = asyncio.Semaphore(cfg.concurrency)
    start_time = time.time()
    done_count = 0

    section("Checking")
    info(f"{len(remaining)} usernames | {len(cfg.proxies)} proxies | {cfg.concurrency} workers")

    async def _worker(username: str):
        nonlocal done_count, _rate_count
        async with sem:
            result, name = await checker.check(username)

            async with _checked_lock:
                _checked_file.write(f"{name}\n")
                _checked_file.flush()

            if result == "HIT":
                async with _hits_lock:
                    _hits_file.write(f"{name}\n")
                    _hits_file.flush()
                ok(f"AVAILABLE: {name}")
            elif result == "TAKEN":
                async with _taken_lock:
                    _taken_file.write(f"{name}\n")
                    _taken_file.flush()
            elif result == "RATE":
                _rate_count += 1
                if _rate_count >= 5:
                    checker.open_circuit(3)
                    _rate_count = 0

            done_count += 1

    tasks = [asyncio.create_task(_worker(u)) for u in remaining]

    async def _progress_loop():
        while not all(t.done() for t in tasks):
            await asyncio.sleep(2)
            elapsed = time.time() - start_time
            rps = done_count / elapsed if elapsed > 0 else 0
            await stats.set_rps(rps)
            pct = done_count / len(remaining) * 100
            console.print(
                f"  [{C.PRIMARY}]{done_count}/{len(remaining)}[/] "
                f"[{C.SUCCESS}]{stats.works}[/] hit | "
                f"[{C.DANGER}]{stats.taken}[/] taken | "
                f"[{C.MUTED}]{rps:.0f} rps[/] | "
                f"[{C.MUTED}]{pct:.1f}%[/]"
            )

    progress = asyncio.create_task(_progress_loop())
    await asyncio.gather(*tasks)
    progress.cancel()

    await checker.flush_remaining()
    await checker.close()

    _hits_file.close()
    _taken_file.close()
    _checked_file.close()

    duration = time.time() - start_time
    snap = await stats.snapshot()
    final_summary(snap, duration)

    if snap["works"] > 0:
        console.print(f"\n  [{C.SUCCESS}]Hits saved to results/hits.txt[/]")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        try:
            from ui import console
            console.print(f"\n[bold red]Fatal error:[/] {e}")
            traceback.print_exc()
        except Exception:
            print(f"Fatal error: {e}")
            traceback.print_exc()
        input("\nPress Enter to exit...")
