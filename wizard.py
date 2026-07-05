#!/usr/bin/env python3
"""Klatom – Setup wizard. Loads from GitHub + proxy scraping."""

from __future__ import annotations

import asyncio
import itertools
import logging
import random
import re
import sys
import time
import warnings
from pathlib import Path

for _name in ("aiohttp", "aiohttp.client", "aiohttp.access", "aiohttp.internal"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", message=".*[Uu]nclosed.*")
warnings.filterwarnings("ignore", message=".*[Cc]onnection.*")

import aiohttp
from rich.prompt import Confirm, IntPrompt, Prompt

from config import (
    DATA_DIR, MAX_CONCURRENCY, PROJECT_ROOT, USERNAME_CHARS,
    AppSettings, Config, RunConfig, ensure_dir, is_valid_username,
)
from ui import (
    banner, card, config_summary, console, fail, info, ok,
    progress_steps, section, warn_card,
)
from github_loader import fetch_names, fetch_all, decrypt_url

_PROXY_RE = re.compile(
    r"^(?:https?://)?(?:[^@\s]+@)?[a-zA-Z0-9](?:[a-zA-Z0-9\-.]*[a-zA-Z0-9])?:\d{1,5}$"
)

PROXY_SOURCES = [
    ("mmpx12", "https://raw.githubusercontent.com/mmpx12/proxy-list/master/https_proxies.txt"),
    ("monosans", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"),
    ("hookzof", "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt"),
    ("ryuken", "https://raw.githubusercontent.com/ryuken/dank-proxy-list/master/http.txt"),
    ("clarketm", "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt"),
    ("sunny9577", "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt"),
    ("rahuldk13", "https://raw.githubusercontent.com/rahuldk13/Proxy-List/master/http_proxies.txt"),
    ("ShiftyTR", "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt"),
    ("roosterkid", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt"),
    ("ErcinDedeworken", "https://raw.githubusercontent.com/ErcinDedeworken/Proxy-List/main/http_proxies.txt"),
    ("officialputuid", "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/https/https.txt"),
    ("ZaeVInne", "https://raw.githubusercontent.com/ZaeVInne/proxies-list/main/http_proxies.txt"),
    ("Tsuk1oko", "https://raw.githubusercontent.com/Tsuk1oko/Proxy-List/main/http.txt"),
    ("yosefben", "https://raw.githubusercontent.com/yosefben/proxy-list/main/http_proxies.txt"),
    ("xhelporg", "https://raw.githubusercontent.com/xhelporg/xhelp-free-proxy-list/main/http_proxies.txt"),
    ("xhelporg-https", "https://raw.githubusercontent.com/xhelporg/xhelp-free-proxy-list/main/https_proxies.txt"),
    ("theriturajps", "https://raw.githubusercontent.com/theriturajps/proxy-list/main/proxies.txt"),
    ("jetkai", "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies.txt"),
    ("proxy4parsing", "https://raw.githubusercontent.com/proxy4parsing/proxy-list/main/http_proxies.txt"),
    ("proxy4parsing-https", "https://raw.githubusercontent.com/proxy4parsing/proxy-list/main/https_proxies.txt"),
    ("AsuDev1", "https://raw.githubusercontent.com/AsuDev1/Free-Proxy-List/main/https_proxies.txt"),
    ("monosans-socks5", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt"),
    ("mmpx12-socks", "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks_proxies.txt"),
    ("rcx", "https://raw.githubusercontent.com/rcx/proxy-list/master/http_proxies.txt"),
    ("prxchk", "https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt"),
    ("ALIILM", "https://raw.githubusercontent.com/ALIILM/proxy-list/main/http.txt"),
    ("faugry", "https://raw.githubusercontent.com/faugry/proxy-list/main/proxy-list-port-3128-http-https.txt"),
    ("Havoc0x", "https://raw.githubusercontent.com/Havoc0x/proxy-list/main/http.txt"),
    ("cluosh", "https://raw.githubusercontent.com/cluosh/proxy-list/main/https_proxies.txt"),
    ("secnets", "https://raw.githubusercontent.com/secnets/proxy-list/master/http.txt"),
    ("MurkMINT", "https://raw.githubusercontent.com/MurkMINT/proxy-list/main/http.txt"),
    ("WeebVPN", "https://raw.githubusercontent.com/WeebVPN/Proxy-list/main/http_proxies.txt"),
    ("HBSB", "https://raw.githubusercontent.com/HBSB/proxy-list/master/http.txt"),
    ("cyclicuis", "https://raw.githubusercontent.com/cyclicuis/GrabProxies/main/http_proxies.txt"),
    ("Racc-e", "https://raw.githubusercontent.com/Racc-e/Proxy-List/main/http.txt"),
    ("pavanshukla01", "https://raw.githubusercontent.com/pavanshukla01/proxy-list/main/http.txt"),
    ("cluosh-https", "https://raw.githubusercontent.com/cluosh/proxy-list/main/https_proxies.txt"),
    ("mohamedelshorbagy", "https://raw.githubusercontent.com/mohamedelshorbagy/ProxyList/main/free-proxy-list.txt"),
    ("ErcinDedeworken-https", "https://raw.githubusercontent.com/ErcinDedeworken/proxy-list/main/https_proxies.txt"),
    ("officialputuid-socks", "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks5/socks5.txt"),
    ("roosterkid-socks", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt"),
    ("shifty-tr", "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt"),
    ("ZaeVInne-socks", "https://raw.githubusercontent.com/ZaeVInne/proxy-list/main/socks5_proxies.txt"),
    ("pavanshukla01-socks", "https://raw.githubusercontent.com/pavanshukla01/proxy-list/main/socks5.txt"),
    ("cyclicuis-socks", "https://raw.githubusercontent.com/cyclicuis/GrabProxies/main/socks_proxies.txt"),
    ("Racc-e-socks", "https://raw.githubusercontent.com/Racc-e/Proxy-List/main/socks5.txt"),
    ("mohamedelshorbagy-socks", "https://raw.githubusercontent.com/mohamedelshorbagy/ProxyList/main/socks5-proxy-list.txt"),
    ("mmpx12-socks5", "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5_proxies.txt"),
    ("monosans-socks5v2", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt"),
]


async def setup_wizard(config: Config, settings: AppSettings) -> RunConfig:
    console.clear()
    console.print(banner())
    console.print()
    console.print(progress_steps(0))

    section("Proxies")
    proxies, remove_bad, scraped = await _step_proxies(config)

    console.print()
    console.print(progress_steps(1))
    usernames = await _step_usernames(config)

    console.print()
    console.print(progress_steps(2))
    concurrency, timeout = _step_speed(proxies, scraped)

    console.print()
    console.print(progress_steps(3))
    webhook_url, webhook_msg = _step_webhook(config)

    config_summary(len(proxies), len(usernames), concurrency, timeout, webhook_url)

    return RunConfig(
        proxies=proxies, remove_bad=remove_bad, usernames=usernames,
        concurrency=concurrency, timeout=timeout, scraped=scraped,
        webhook_url=webhook_url, webhook_msg=webhook_msg,
    )


async def _step_proxies(config: Config) -> tuple[list[str], bool, bool]:
    raw = Prompt.ask(
        f"[{C.PRIMARY}](f)ile[/]  [{C.PRIMARY}](p)aste[/]  [{C.PRIMARY}](s)crape[/]  [{C.PRIMARY}](g)itHub[/]  [{C.PRIMARY}](t)est speed[/]  [{C.PRIMARY}](n)one[/]",
        choices=["f", "p", "s", "g", "t", "n"], default="s",
    )
    mode = raw

    if mode == "f":
        path = Prompt.ask("Path to proxy file", default="data/proxies.txt")
        p = Path(path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        proxies = [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
        if proxies:
            ok(f"Loaded {len(proxies)} proxies")
        else:
            fail("File empty — switching to scrape")
            mode = "s"

    if mode == "p":
        info("Paste proxies (empty line to finish):")
        lines = []
        while True:
            line = input("  > ")
            if not line.strip():
                break
            lines.append(line.strip())
        proxies = [l for l in lines if _PROXY_RE.match(l)]
        if proxies:
            ok(f"Got {len(proxies)} valid proxies")
        else:
            fail("No valid proxies — switching to scrape")
            mode = "s"

    if mode == "g":
        proxies = []
        for name, url in PROXY_SOURCES[:5]:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                        if r.status == 200:
                            text = await r.text()
                            found = [l.strip() for l in text.splitlines() if l.strip() and _PROXY_RE.match(l.strip())]
                            proxies.extend(found)
                            ok(f"{name}: {len(found)}")
            except Exception:
                fail(f"{name}: failed")
        if proxies:
            ok(f"Total: {len(proxies)} proxies from GitHub")
        else:
            fail("No proxies scraped — switching to none")
            mode = "n"

    if mode == "s":
        proxies = await _scrape_proxies()

    if mode == "t":
        proxies = await _scrape_proxies()
        if proxies:
            ok(f"Testing {len(proxies)} proxies for speed...")
            fast = await speed_test_proxies(proxies)
            if fast:
                proxies = fast
                ok(f"{len(proxies)} fast proxies selected")
            else:
                warn_card("Speed test found no fast proxies — using all scraped.")

    if mode == "n":
        info("Running without proxies — 1 worker with delay")
        return [], False, False

    remove_bad = Confirm.ask(f"[{C.PRIMARY}]Auto-remove dead proxies?[/]", default=True)
    return proxies, remove_bad, mode in ("s", "t")


async def _scrape_proxies() -> list[str]:
    all_proxies = []
    info(f"Scraping from {len(PROXY_SOURCES)} sources...")

    sem = asyncio.Semaphore(30)
    done = 0

    async def fetch_one(name: str, url: str) -> list[str]:
        nonlocal done
        async with sem:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                        done += 1
                        if r.status == 200:
                            text = await r.text()
                            return [l.strip() for l in text.splitlines()
                                    if l.strip() and _PROXY_RE.match(l.strip())]
            except Exception:
                done += 1
            return []

    tasks = [fetch_one(name, url) for name, url in PROXY_SOURCES]
    results = await asyncio.gather(*tasks)

    for r in results:
        all_proxies.extend(r)

    unique = list(dict.fromkeys(all_proxies))
    ok(f"Scraped {len(unique)} unique proxies")
    return unique


async def _step_usernames(config: Config, _depth: int = 0) -> list[str]:
    if _depth > 3:
        fail("Too many failed attempts — returning empty list")
        return []

    raw = Prompt.ask(
        f"[{C.PRIMARY}](g)itHub[/]  [{C.PRIMARY}](f)ile[/]  [{C.PRIMARY}](p)aste[/]  [{C.PRIMARY}](r)andom generate[/]",
        choices=["g", "f", "p", "r"], default="g",
    )

    if raw == "g":
        info("Fetching usernames from GitHub...")
        try:
            names = await fetch_names()
            if names:
                ok(f"Loaded {len(names)} usernames from GitHub")
                return names
            else:
                fail("GitHub fetch failed — try file, paste, or generate")
                return await _step_usernames(config, _depth + 1)
        except Exception as e:
            fail(f"GitHub error: {e}")
            return await _step_usernames(config, _depth + 1)

    if raw == "f":
        path = Prompt.ask("Path to username file", default="data/names.txt")
        p = Path(path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        if p.exists():
            names = [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
            if names:
                ok(f"Loaded {len(names)} usernames")
                return names
        fail("File empty or missing")
        return await _step_usernames(config, _depth + 1)

    if raw == "p":
        info("Paste usernames (empty line to finish):")
        names = []
        while True:
            line = input("  > ")
            if not line.strip():
                break
            if is_valid_username(line.strip()):
                names.append(line.strip())
        if names:
            ok(f"Got {len(names)} valid usernames")
            return names
        fail("No valid usernames")
        return await _step_usernames(config, _depth + 1)

    if raw == "r":
        return _generate_usernames()

    return []


def _generate_usernames() -> list[str]:
    length = IntPrompt.ask("Username length", default=4, choices=["2", "3", "4", "5"])
    total = len(USERNAME_CHARS) ** length
    target = min(50000, total)

    ok(f"Generating {target} random {length}-char usernames (of {total:,} possible)...")
    seen: set[str] = set()
    usernames: list[str] = []
    attempts = 0
    max_attempts = target * 20
    while len(usernames) < target and attempts < max_attempts:
        attempts += 1
        cand = "".join(random.choices(USERNAME_CHARS, k=length))
        if cand not in seen and is_valid_username(cand):
            seen.add(cand)
            usernames.append(cand)

    ok(f"Generated {len(usernames)} {length}-char usernames")

    names_path = DATA_DIR / "names.txt"
    names_path.parent.mkdir(parents=True, exist_ok=True)
    names_path.write_text("\n".join(usernames), encoding="utf-8")

    return usernames


async def speed_test_proxies(proxies: list[str]) -> list[str]:
    """Test proxies concurrently, return only working ones sorted by speed."""
    from config import ENDPOINT

    test_pool = list(proxies)
    total = len(test_pool)
    info(f"Testing {total} proxies for speed...")

    sem = asyncio.Semaphore(200)
    results: list[tuple[str, float]] = []
    tested = 0
    lock = asyncio.Lock()

    async def _test_one(sess: aiohttp.ClientSession, proxy_raw: str) -> None:
        nonlocal tested
        async with sem:
            proxy = proxy_raw.strip()
            if not proxy.startswith("http"):
                proxy = f"http://{proxy}"
            try:
                start = time.time()
                async with sess.post(
                    ENDPOINT,
                    json={"username": "a"},
                    proxy=proxy,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status in (200, 201, 204, 400, 429):
                        latency = time.time() - start
                        async with lock:
                            results.append((proxy_raw, latency))
            except Exception:
                pass
            async with lock:
                tested += 1
            if tested % 200 == 0 or tested == total:
                info(f"  {tested}/{total} tested")

    connector = aiohttp.TCPConnector(limit=200, limit_per_host=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=5),
        trust_env=False,
    ) as sess:
        tasks = [_test_one(sess, p) for p in test_pool]
        await asyncio.gather(*tasks)

    if not results:
        fail("No working proxies found")
        return []

    results.sort(key=lambda x: x[1])

    ok(f"{len(results)}/{total} alive (sorted by speed)")
    for proxy, lat in results[:5]:
        console.print(f"  [{C.SUCCESS}]{lat:.2f}s[/] {proxy}")

    return [p for p, _ in results]


def _step_speed(proxies: list[str], scraped: bool) -> tuple[int, int]:
    if not proxies:
        info("Proxyless mode — 1 worker with delay.")
        delay = IntPrompt.ask("Delay between requests (seconds)", default=5)
        return 1, delay

    if scraped:
        info("Free proxy mode — high concurrency.")
        default_conc = min(200, max(10, len(proxies) * 3))
        conc = IntPrompt.ask("Concurrent workers", default=default_conc)
        if conc > MAX_CONCURRENCY:
            warn_card(f"Capped at {MAX_CONCURRENCY}")
            conc = MAX_CONCURRENCY
        timeout = IntPrompt.ask("Request timeout (seconds)", default=5)
        return conc, timeout

    default_conc = min(MAX_CONCURRENCY, max(10, len(proxies) * 5))
    conc = IntPrompt.ask("Concurrent workers", default=default_conc)
    if conc > MAX_CONCURRENCY:
        warn_card(f"Capped at {MAX_CONCURRENCY}")
        conc = MAX_CONCURRENCY
    timeout = IntPrompt.ask("Request timeout (seconds)", default=10)
    return conc, timeout


def _step_webhook(config: Config) -> tuple[str | None, str | None]:
    saved_url = config.get("webhook")
    saved_msg = config.get("webhook_message", "**<name>** available | <t:time:R>")

    if saved_url:
        masked = config.get_masked("webhook", "•••")
        console.print(f"[{C.PRIMARY}]Webhook saved:[/] {masked}")
        choice = Prompt.ask(
            f"[{C.PRIMARY}]Webhook:[/] (u)se  (c)hange  (d)isable",
            choices=["u", "c", "d"], default="u",
        ).strip().lower()

        if choice == "d":
            config.set("webhook", "")
            config.set("webhook_message", "")
            ok("Webhook disabled")
            return None, None
        if choice == "c":
            return _prompt_webhook(config)
        return saved_url, saved_msg

    use = Confirm.ask(f"[{C.PRIMARY}]Set up webhook?[/]", default=False)
    if use:
        return _prompt_webhook(config)
    return None, None


def _prompt_webhook(config: Config) -> tuple[str | None, str | None]:
    url = Prompt.ask("Webhook URL")
    if not url.strip():
        info("Empty — webhook disabled.")
        return None, None
    msg = Prompt.ask("Message template", default="**<name>** available | <t:time:R>")
    config.set("webhook", url)
    config.set("webhook_message", msg)
    ok("Webhook saved")
    return url, msg
