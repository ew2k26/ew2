#!/usr/bin/env python3
"""KLATOM v3.3 - Discord username availability checker."""

from __future__ import annotations

import asyncio.sslproto as _sslproto

_orig_eof = _sslproto.SSLProtocol.eof_received

def _safe_eof(self):
    try:
        return _orig_eof(self)
    except RuntimeError:
        return False

_sslproto.SSLProtocol.eof_received = _safe_eof

import asyncio.proactor_events as _proactor
_orig_cl = _proactor._ProactorBasePipeTransport._call_connection_lost
def _silent_cl(self, exc):
    try:
        _orig_cl(self, exc)
    except ConnectionResetError:
        pass
_proactor._ProactorBasePipeTransport._call_connection_lost = _silent_cl

import logging, warnings
for _n in ("aiohttp", "aiohttp.client", "aiohttp.access", "aiohttp.internal"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", message=".*[Uu]nclosed.*")
warnings.filterwarnings("ignore", message=".*[Cc]onnection.*")

import ctypes
try:
    k = ctypes.windll.kernel32
    u = ctypes.windll.user32
    h = k.GetConsoleWindow()
    if h:
        u.SetWindowTextW(h, "KLATOM v" + str(__import__('config').VERSION))
except Exception:
    pass

import argparse
import asyncio
import sys
import time
from pathlib import Path

import aiohttp
from rich.live import Live

from config import (
    PROJECT_ROOT,
    DATA_DIR,
    LOGS_DIR,
    MAX_CONCURRENCY,
    RESULTS_DIR,
    AppSettings,
    Config,
    RunConfig,
    Stats,
    ensure_dir,
    ensure_file,
    load_lines,
)
from proxy import ProxyManager
from engine import (
    Checker,
    CircuitBreaker,
    WebhookSender,
    set_debug,
    dbg,
)
from ui import (
    C,
    banner,
    console,
    final_summary,
    live_card,
    speed_test_progress,
    speed_test_result,
)
from wizard import setup_wizard


def parse_args() -> AppSettings:
    parser = argparse.ArgumentParser(description="KLATOM - Discord username checker")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("-n", "--no-wizard", action="store_true")
    parser.add_argument("-m", "--mod", action="store_true", help="Launch mod panel")
    parser.add_argument("-t", "--terminal", action="store_true", help="Use terminal UI instead of GUI")
    parser.add_argument("--version", action="version", version=f"KLATOM v{__import__('config').VERSION}")
    args = parser.parse_args()
    return AppSettings(debug=args.debug, no_wizard=args.no_wizard, mod=args.mod, terminal=args.terminal)


async def _rps_calculator(stats: Stats, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        prev_req = stats.requests
        prev_done = stats.works + stats.taken
        await asyncio.sleep(1)
        await stats.set_rps(float(stats.requests - prev_req))
        await stats.set_checks_rps(float(stats.works + stats.taken - prev_done))


async def _run_checker(cfg: RunConfig, settings: AppSettings) -> None:
    _hits_path = RESULTS_DIR / "hits.txt"
    _hits_path.parent.mkdir(parents=True, exist_ok=True)
    _hits_file = _hits_path.open("a", encoding="utf-8")
    _hits_lock = asyncio.Lock()

    pm = ProxyManager(cfg.proxies, remove_on_fail=cfg.remove_bad_proxies, scored=cfg.scraped)
    stats = Stats()
    start_time = time.time()
    proxyless = not cfg.proxies

    if cfg.concurrency > MAX_CONCURRENCY:
        cfg.concurrency = MAX_CONCURRENCY

    # Speed test scraped proxies before starting
    working_proxies = 0
    if cfg.scraped and len(cfg.proxies) > 10:
        console.print()
        console.print(f"[{C.PRIMARY}]Speed testing {len(cfg.proxies)} proxies...[/]")
        console.print()

        def _on_progress(tested, total, working):
            speed_test_progress(tested, total, working)

        results = await pm.speed_test(
            concurrency=200,
            timeout=8.0,
            on_progress=_on_progress,
        )
        console.print()
        working_proxies = await pm.apply_speed_results(results, remove_slow=True, max_latency_ms=3000)
        speed_test_result(results)

        if working_proxies == 0:
            console.print(f"[{C.DANGER}]No working proxies found. Try again or use different sources.[/]")
            return

        console.print(f"[{C.SUCCESS}]Using {working_proxies} fast proxies[/]")
        console.print()

    try:
        import resource as _resource
        _soft, _hard = _resource.getrlimit(_resource.RLIMIT_NOFILE)
        _resource.setrlimit(_resource.RLIMIT_NOFILE, (_hard if _hard > 1024 else 4096, _hard))
    except Exception:
        pass

    connector = aiohttp.TCPConnector(
        limit=MAX_CONCURRENCY * 2,
        limit_per_host=0,
        force_close=False,
        enable_cleanup_closed=True,
        ttl_dns_cache=300,
    )
    session_timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=30)
    session = aiohttp.ClientSession(
        connector=connector,
        trust_env=False,
        timeout=session_timeout,
    )

    cb: CircuitBreaker | None = None
    paused = False
    if pm.is_single and not pm.is_proxyless:
        async def _on_circuit_open():
            nonlocal paused
            paused = True
            await stats.inc_circuit_open()
            await asyncio.sleep(2.0)
            paused = False
        cb = CircuitBreaker(threshold=10, window=2.0, cooldown=2.0, on_open=_on_circuit_open)

    http_timeout = 5 if proxyless else cfg.timeout
    checker = Checker(pm, timeout=http_timeout, scraped=cfg.scraped, circuit_breaker=cb, stats=stats)

    webhook: WebhookSender | None = None
    if cfg.webhook_url and cfg.webhook_message:
        webhook = WebhookSender(cfg.webhook_url, cfg.webhook_message, session, start_time)

    names = list(cfg.usernames)
    total = len(names)
    _idx_lock = asyncio.Lock()
    _next_idx = 0

    async def _next_task() -> tuple[int, str] | None:
        nonlocal _next_idx
        async with _idx_lock:
            if _next_idx >= total:
                return None
            i = _next_idx
            _next_idx += 1
        return i, names[i]

    recent_hits: list[str] = []
    request_log: list[str] = []

    async def _worker(worker_id: int) -> None:
        while True:
            t = await _next_task()
            if t is None:
                return
            idx, name = t
            try:
                result, data, code = await checker.check(session, name)
                if result is True:
                    await stats.inc_works()
                    async with _hits_lock:
                        _hits_file.write(f"{name}\n")
                        _hits_file.flush()
                    recent_hits.append(name)
                    request_log.append(f"[{C.SUCCESS}]\u2713[/] {name}")
                    if webhook:
                        webhook.enqueue(name)
                elif result is False:
                    await stats.inc_taken()
                    request_log.append(f"[{C.DANGER}]\u2717[/] {name}")
                elif result == "EXHAUSTED":
                    request_log.append(f"[{C.WARNING}]![/] proxies exhausted")
                else:
                    await stats.inc_errors()
                    request_log.append(f"[{C.DANGER}]x[/] {name}")
                if proxyless:
                    await asyncio.sleep(cfg.timeout)
            except Exception:
                await stats.inc_errors()
                request_log.append(f"[{C.DANGER}]!![/] {name}")
                continue

    stop_rps = asyncio.Event()
    rps_task = asyncio.create_task(_rps_calculator(stats, stop_rps))
    webhook_task = asyncio.create_task(webhook.run()) if webhook else None

    pending: set[asyncio.Task] = {
        asyncio.create_task(_worker(i)) for i in range(cfg.concurrency)
    }

    def _live_render():
        return live_card(
            done=stats.works + stats.taken,
            total=total,
            works=stats.works,
            taken=stats.taken,
            requests=stats.requests,
            ratelimited=stats.ratelimited,
            circuit_opens=stats.circuit_opens,
            rps=stats.rps,
            checks_rps=stats.checks_rps,
            elapsed=time.time() - start_time,
            proxy_alive=pm.alive_count,
            paused=paused,
            errors=stats.errors,
            avg_latency=pm.avg_latency * 1000 if pm.avg_latency > 0 else 0,
            recent=recent_hits,
            feed=request_log,
        )

    console.print()
    try:
        with Live(_live_render(), refresh_per_second=4, console=console) as live:
            while pending:
                await asyncio.sleep(0.3)
                pending = {w for w in pending if not w.done()}
                while _next_idx < total and len(pending) < cfg.concurrency:
                    pending.add(asyncio.create_task(_worker(len(pending))))
                if not pending and _next_idx >= total:
                    break
                live.update(_live_render())
    except asyncio.CancelledError:
        pass
    finally:
        stop_rps.set()
        rps_task.cancel()
        for w in pending:
            w.cancel()
        if webhook_task:
            webhook_task.cancel()
        await asyncio.sleep(0)

    elapsed = time.time() - start_time
    snap = await stats.snapshot()

    _hits_file.close()
    await session.close()

    final_summary(
        requests=snap["requests"],
        works=snap["works"],
        taken=snap["taken"],
        ratelimited=snap["ratelimited"],
        circuit_opens=snap["circuit_opens"],
        elapsed=elapsed,
        peak_rps=snap["peak_rps"],
        best_streak=snap["best_streak"],
        errors=snap["errors"],
    )


def main() -> None:
    settings = parse_args()
    set_debug(settings.debug)

    ensure_dir(DATA_DIR, LOGS_DIR, RESULTS_DIR)
    ensure_file(DATA_DIR / "config.json")
    ensure_file(DATA_DIR / "proxies.txt")
    ensure_file(DATA_DIR / "names_to_check.txt")
    ensure_file(LOGS_DIR / "error.txt", clean=True)

    config = Config()

    # Auto-detect mod build by exe name
    exe_name = ""
    try:
        import sys as _sys
        if getattr(_sys, 'frozen', False):
            exe_name = Path(_sys.executable).stem.lower()
    except Exception:
        pass

    is_mod = settings.mod or "mod" in exe_name

    if is_mod:
        from test_mode import main as mod_main
        mod_main()
        return

    # Launch GUI by default (unless --terminal or --no-wizard)
    if not settings.terminal and not settings.no_wizard:
        try:
            import tkinter as _tk
            _tk.WmWithdraw(_tk._default_root or _tk.Tk())
        except Exception:
            pass
        try:
            from gui import main as gui_main
            gui_main()
            return
        except Exception as e:
            console.print(f"[{C.WARNING}]GUI failed ({e}), falling back to terminal[/]")

    try:
        # Authentication check
        from auth import check_auth
        webhook_url = config.get("webhook", "")
        authenticated, token = check_auth(webhook_url=webhook_url)
        if not authenticated:
            console.print(f"\n[{C.DANGER}]Authentication failed. Exiting.[/]")
            sys.exit(0)

        if settings.no_wizard:
            proxy_file = config.get("last_proxy_file", str(DATA_DIR / "proxies.txt"))
            names_file = config.get("last_names_file", str(DATA_DIR / "names_to_check.txt"))
            proxies = load_lines(proxy_file)
            usernames = load_lines(names_file)
            if not proxies:
                console.print(f"[{C.WARNING}]No proxies found - running proxyless.[/]")
            if not usernames:
                console.print(f"[{C.DANGER}]No usernames found. Run without --no-wizard first.[/]")
                sys.exit(1)
            run_config = RunConfig(
                proxies=proxies,
                remove_bad_proxies=config.get("remove_proxies", False),
                usernames=usernames,
                concurrency=config.get("concurrency", 50),
                timeout=config.get("timeout", 10),
                scraped=False,
                webhook_url=config.get("webhook"),
                webhook_message=config.get("webhook_message"),
            )
            console.print(f"[{C.MUTED}]Skipping wizard - {len(proxies)} proxies, {len(usernames)} usernames[/]")
        else:
            run_config = asyncio.run(setup_wizard(config, settings))

        asyncio.run(_run_checker(run_config, settings))
    except (EOFError, KeyboardInterrupt):
        console.print(f"\n[{C.WARNING}]Aborted.[/]")
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        try:
            console.print(f"\n[bold red]Fatal error:[/] {e}")
            traceback.print_exc()
        except Exception:
            print(f"Fatal error: {e}")
            traceback.print_exc()
        input("\nPress Enter to exit...")
