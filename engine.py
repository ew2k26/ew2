#!/usr/bin/env python3
"""KLATOM v3.3 - Checker engine, circuit breaker, error aggregation, webhook."""

from __future__ import annotations

import asyncio
import sys
import time

import aiohttp

from proxy import ProxyManager

_debug: bool = False


def set_debug(enabled: bool) -> None:
    global _debug
    _debug = enabled


def dbg(*args, **kwargs) -> None:
    if _debug:
        print(*args, file=sys.stderr, flush=True, **kwargs)


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    def __init__(
        self,
        threshold: int = 8,
        window: float = 2.0,
        cooldown: float = 2.0,
        on_open=None,
    ) -> None:
        self.threshold = threshold
        self.window = window
        self.cooldown = cooldown
        self._failures: list[float] = []
        self._lock = asyncio.Lock()
        self._open_until: float = 0.0
        self._on_open = on_open

    async def record_failure(self) -> None:
        async with self._lock:
            now = time.time()
            self._failures.append(now)
            self._failures = [t for t in self._failures if now - t < self.window]
            if len(self._failures) >= self.threshold:
                self._open_until = now + self.cooldown
                if self._on_open:
                    import asyncio as _asyncio
                    _asyncio.ensure_future(self._on_open())

    async def wait_if_open(self) -> None:
        now = time.time()
        if now < self._open_until:
            wait = self._open_until - now
            dbg(f"[cb] circuit open, waiting {wait:.1f}s")
            await asyncio.sleep(wait)


# ---------------------------------------------------------------------------
# ErrorAggregator
# ---------------------------------------------------------------------------

class ErrorAggregator:
    def __init__(
        self,
        flush_interval: float = 30.0,
        flush_count: int = 500,
    ) -> None:
        self.flush_interval = flush_interval
        self.flush_count = flush_count
        self._lock = asyncio.Lock()
        self._counters: dict[str, int] = {}
        self._last_flush = time.time()

    async def inc(self, category: str) -> None:
        async with self._lock:
            self._counters[category] = self._counters.get(category, 0) + 1
            total = sum(self._counters.values())
            if total >= self.flush_count or (time.time() - self._last_flush) >= self.flush_interval:
                await self._flush_locked()

    async def flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    async def _flush_locked(self) -> None:
        self._counters.clear()
        self._last_flush = time.time()


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------

from config import ENDPOINT


class Checker:
    """Async username checker with latency tracking and fast fallback."""

    MAX_RETRIES = 15
    MAX_RETRIES_ROTATING = 100
    STATIC_TOTAL_TIMEOUT = 90.0

    def __init__(
        self,
        proxy_manager: ProxyManager,
        timeout: int = 10,
        scraped: bool = False,
        circuit_breaker: CircuitBreaker | None = None,
        stats=None,
    ) -> None:
        self.pm = proxy_manager
        self.timeout = timeout
        self._err = ErrorAggregator()
        self._rotating = proxy_manager.is_single
        self._scraped = scraped
        self._cb = circuit_breaker
        self._stats = stats

        if scraped:
            self._max_retries = 1
        elif self._rotating:
            self._max_retries = self.MAX_RETRIES_ROTATING
        else:
            self._max_retries = self.MAX_RETRIES

    async def check(
        self,
        session: aiohttp.ClientSession,
        username: str,
    ) -> tuple[bool | str, dict | None, int | None]:
        """Check a single username.

        Returns:
            (True, data, code)  - available
            (False, data, code) - taken or invalid
            ("EXHAUSTED", None, None) - all proxies dead
            ("ERROR", None, None) - max retries exceeded
        """
        attempt = 0
        started = time.time()

        while True:
            proxy = await self.pm.next()
            if proxy is None and not self.pm.is_proxyless:
                return ("EXHAUSTED", None, None)

            attempt += 1
            if attempt > self._max_retries:
                return ("ERROR", None, None)

            if not self._rotating and time.time() - started > self.STATIC_TOTAL_TIMEOUT:
                return ("ERROR", None, None)

            if self._stats:
                await self._stats.inc_requests()

            req_start = time.time()

            try:
                if self._scraped:
                    _timeout = aiohttp.ClientTimeout(total=5, sock_connect=4)
                elif self._rotating:
                    _timeout = aiohttp.ClientTimeout(
                        total=min(self.timeout, 5), sock_connect=4,
                    )
                else:
                    _timeout = aiohttp.ClientTimeout(
                        total=self.timeout, sock_connect=6,
                    )

                async with session.post(
                    ENDPOINT,
                    json={"username": username},
                    proxy=proxy,
                    headers={"Content-Type": "application/json"},
                    timeout=_timeout,
                ) as resp:
                    latency = time.time() - req_start
                    # record latency for speed-based proxy selection
                    if proxy and self._scraped:
                        self.pm.record_latency(proxy, latency)

                    dbg(f"  [{attempt}] {username} -> HTTP {resp.status}")

                    if resp.status == 429:
                        try:
                            data = await resp.json()
                            cooldown = data.get("retry_after", 5)
                        except Exception:
                            cooldown = 5

                        if self._scraped:
                            if proxy:
                                self.pm.set_rate_limit(proxy, cooldown)
                            if self._stats:
                                await self._stats.inc_ratelimited()
                            continue

                        if self._rotating:
                            if self._stats:
                                await self._stats.inc_ratelimited()
                            continue

                        if self._stats:
                            await self._stats.inc_ratelimited()
                        if proxy:
                            await self.pm.set_cooldown(proxy, cooldown)
                        else:
                            await self._err.inc("429_proxyless")
                            await asyncio.sleep(cooldown)
                        continue

                    if resp.status in (200, 201, 204):
                        try:
                            data = await resp.json()
                        except Exception:
                            data = {}
                        taken = data.get("taken", True)
                        if self._scraped and proxy:
                            self.pm.score_hit(proxy)
                        return (not taken, data, resp.status)

                    if resp.status == 400:
                        try:
                            data = await resp.json()
                        except Exception:
                            data = {}
                        return (False, data, resp.status)

                    # unknown status - short retry
                    await self._err.inc(f"http_{resp.status}")
                    await asyncio.sleep(0.3)
                    continue

            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                OSError,
            ) as exc:
                dbg(f"  [{attempt}] {username} -> {type(exc).__name__}")

                if self._scraped:
                    if proxy:
                        self.pm.score_miss(proxy)
                    continue

                if self._rotating:
                    if self._cb:
                        await self._cb.record_failure()
                        await self._cb.wait_if_open()
                    backoff = min(attempt * 0.2, 2.0)
                    await asyncio.sleep(backoff)
                    continue

                await self._err.inc("proxy_conn_err")
                await self.pm.set_cooldown(proxy, 2)
                backoff = min(attempt * 0.1, 3.0)
                await asyncio.sleep(backoff)
                continue

            except Exception as exc:
                dbg(f"  [{attempt}] {username} -> {type(exc).__name__}: {exc!s:.100}")
                await asyncio.sleep(0.2)
                continue


# ---------------------------------------------------------------------------
# WebhookSender
# ---------------------------------------------------------------------------

from config import Stats


class WebhookSender:
    """Sends found usernames to Discord webhook in batches with stats."""

    DISCORD_MAX_CHARS = 1900
    BATCH_SIZE = 20
    FLUSH_INTERVAL = 2.5

    def __init__(
        self,
        webhook_url: str,
        message_template: str,
        session: aiohttp.ClientSession,
        start_time: float = 0.0,
    ) -> None:
        self.url = webhook_url
        self.template = message_template
        self.session = session
        self.start_time = start_time
        self._sent: set[str] = set()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._buffer: list[str] = []
        self._buffer_lock = asyncio.Lock()
        self._total_sent = 0

    def enqueue(self, username: str) -> None:
        if username not in self._sent:
            self._sent.add(username)
            self._queue.put_nowait(username)

    async def run(self) -> None:
        last_flush = time.time()

        while True:
            try:
                username = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                async with self._buffer_lock:
                    if self._buffer and time.time() - last_flush >= self.FLUSH_INTERVAL:
                        await self._flush_locked()
                        last_flush = time.time()
                continue

            async with self._buffer_lock:
                self._buffer.append(username)
                count = len(self._buffer)

                hit_lines = [self.template.replace("<name>", n) for n in self._buffer]
                preview = "\n".join(hit_lines)

                should_flush = (
                    count >= self.BATCH_SIZE
                    or len(preview) >= self.DISCORD_MAX_CHARS
                    or (count > 0 and time.time() - last_flush >= self.FLUSH_INTERVAL)
                )

                if should_flush:
                    await self._flush_locked()
                    last_flush = time.time()

    async def _flush_locked(self) -> None:
        if not self._buffer:
            return

        names = list(self._buffer)
        self._buffer.clear()

        now = time.time()
        elapsed = int(now - self.start_time)
        ts_discord = f"<t:{int(now)}:R>"
        mins, secs = divmod(elapsed, 60)
        elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"

        def _fill(n: str) -> str:
            return (
                self.template
                .replace("<name>", n)
                .replace("<t:time:R>", ts_discord)
                .replace("<time>", ts_discord)
                .replace("<elapsed>", elapsed_str)
            )

        lines = [_fill(n) for n in names]
        msg = "\n".join(lines)
        if len(msg) > self.DISCORD_MAX_CHARS:
            safe = msg[: self.DISCORD_MAX_CHARS - 3]
            last_nl = safe.rfind("\n")
            if last_nl > 0:
                msg = safe[:last_nl] + "\n..."
            else:
                msg = safe + "..."

        self._total_sent += len(names)

        payload = {
            "content": msg,
            "username": "KLATOM",
            "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/95/Burning_Yellow_Sunset.jpg/1280px-Burning_Yellow_Sunset.jpg",
        }

        for attempt in range(3):
            try:
                async with self.session.post(self.url, json=payload) as resp:
                    if resp.status == 429:
                        try:
                            data = await resp.json()
                            wait = data.get("retry_after", 5)
                        except Exception:
                            wait = 5
                        await asyncio.sleep(wait)
                        continue
                    if resp.status in (200, 204):
                        return
                    return
            except Exception:
                await asyncio.sleep(1)
