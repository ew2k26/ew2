#!/usr/bin/env python3
"""KLATOM v3.3 - Mod Panel GUI (token management, auth tools, speed test)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from pathlib import Path

from config import DATA_DIR, VERSION

# ── Colors ──

BG = "#0C0C12"
BG2 = "#15151E"
BG3 = "#1C1C28"
BORDER = "#2A2A35"
TXT = "#F0F0F5"
TXT2 = "#8888A0"
MUTED = "#7A7A82"
PRIMARY = "#A855F7"
PRIMARY_D = "#7C3AED"
SUCCESS = "#30D158"
DANGER = "#FF453A"
WARNING = "#FF9F0A"

AUTH_FILE = DATA_DIR / ".auth"
SESSION_FILE = DATA_DIR / ".session"
TOKENS_FILE = DATA_DIR / ".tokens"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _hwid() -> str:
    try:
        parts = [platform.node(), platform.machine(), platform.processor()]
        import uuid
        parts.append(str(uuid.getnode()))
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


class ModApp(tk.Tk):
    """KLATOM Mod Panel GUI."""

    def __init__(self) -> None:
        super().__init__()
        self.title("KLATOM - Mod Panel")
        self.geometry("700x560")
        self.minsize(600, 480)
        self.configure(bg=BG)

        # Center
        self.update_idletasks()
        w, h = 700, 560
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._build_header()
        self._build_nav()
        self._build_body()

        # Show session info by default
        self._show_session()

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=BG2, height=56)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        tf = tk.Frame(header, bg=BG2)
        tf.pack(side="left", padx=20, pady=10)

        tk.Label(tf, text="KL", font=("Segoe UI", 18, "bold"), fg=PRIMARY, bg=BG2).pack(side="left")
        tk.Label(tf, text="ATOM", font=("Segoe UI", 18, "bold"), fg=TXT, bg=BG2).pack(side="left")
        tk.Label(tf, text="  MOD PANEL", font=("Segoe UI", 10, "bold"), fg=WARNING, bg=BG2).pack(side="left", padx=(12, 0))
        tk.Label(tf, text=f"v{VERSION}", font=("Segoe UI", 10), fg=MUTED, bg=BG2).pack(side="left", padx=(8, 0))

        tk.Label(header, text="Admin", font=("Segoe UI", 9), fg=WARNING, bg=BG3, padx=8, pady=2).pack(side="right", padx=20)

    def _build_nav(self) -> None:
        nav = tk.Frame(self, bg=BG3, height=36)
        nav.pack(fill="x")
        nav.pack_propagate(False)

        self._nav_buttons = {}
        for label, cmd in [
            ("Session", self._show_session),
            ("Tokens", self._show_tokens),
            ("Generate", self._show_generate),
            ("Speed Test", self._show_speed_test),
            ("Hits", self._show_hits),
            ("Clear Auth", self._show_clear_auth),
        ]:
            btn = tk.Button(
                nav, text=label, command=cmd,
                font=("Segoe UI", 9), fg=MUTED, bg=BG3,
                activebackground=BORDER, activeforeground=TXT,
                relief="flat", padx=12, pady=4, cursor="hand2",
            )
            btn.pack(side="left", padx=1)
            self._nav_buttons[label] = btn

    def _build_body(self) -> None:
        self._body = tk.Frame(self, bg=BG)
        self._body.pack(fill="both", expand=True)

    def _clear_body(self) -> None:
        for w in self._body.winfo_children():
            w.destroy()

    def _highlight_nav(self, active: str) -> None:
        for label, btn in self._nav_buttons.items():
            if label == active:
                btn.configure(fg=PRIMARY, bg=BG)
            else:
                btn.configure(fg=MUTED, bg=BG3)

    # ── Session Info ──

    def _show_session(self) -> None:
        self._clear_body()
        self._highlight_nav("Session")

        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=20)

        tk.Label(frame, text="Session Info", font=("Segoe UI", 14, "bold"), fg=TXT, bg=BG, anchor="w").pack(fill="x", pady=(0, 16))

        info_frame = tk.Frame(frame, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        info_frame.pack(fill="x", pady=(0, 16))

        hwid = _hwid()

        # Auth data
        auth_data = None
        if AUTH_FILE.exists():
            try:
                from crypto import load_auth
                auth_data = load_auth(AUTH_FILE)
            except Exception:
                pass

        # Session data
        session_data = None
        if SESSION_FILE.exists():
            try:
                from crypto import load_session
                session_data = load_session(SESSION_FILE)
            except Exception:
                pass

        # Tokens count
        tokens_count = 0
        if TOKENS_FILE.exists():
            try:
                tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
                tokens_count = len(tokens)
            except Exception:
                pass

        # Hits count
        hits_count = 0
        hits_file = RESULTS_DIR / "hits.txt"
        if hits_file.exists():
            hits_count = len([l for l in hits_file.read_text(encoding="utf-8").splitlines() if l.strip()])

        rows = [
            ("HWID", hwid, MUTED),
            ("Machine", platform.node(), MUTED),
        ]

        if auth_data:
            token_hashes = auth_data.get("t", [])
            rows.append(("Stored Tokens", f"{len(token_hashes)} (hashed)", PRIMARY))
        else:
            rows.append(("Auth File", "Not found", DANGER))

        if session_data:
            start = session_data.get("ts", 0)
            if start:
                remaining = max(0, 86400 - (time.time() - start))
                if remaining > 0:
                    h = int(remaining // 3600)
                    m = int((remaining % 3600) // 60)
                    s = int(remaining % 60)
                    color = SUCCESS if remaining > 3600 else WARNING
                    rows.append(("Trial Status", "ACTIVE", color))
                    rows.append(("Time Left", f"{h}h {m}m {s}s", color))
                    expires = datetime.now() + timedelta(seconds=remaining)
                    rows.append(("Expires", expires.strftime("%Y-%m-%d %H:%M"), MUTED))
                else:
                    rows.append(("Trial Status", "EXPIRED", DANGER))
            else:
                rows.append(("Trial Status", "Not started", DANGER))
        else:
            rows.append(("Trial Status", "No session", DANGER))

        rows.append(("Tokens File", f"{tokens_count} tokens", PRIMARY))
        rows.append(("Hits Found", str(hits_count), SUCCESS))

        for label, value, color in rows:
            row = tk.Frame(info_frame, bg=BG2)
            row.pack(fill="x", padx=16, pady=6)
            tk.Label(row, text=label, font=("Segoe UI", 10), fg=MUTED, bg=BG2, width=14, anchor="w").pack(side="left")
            tk.Label(row, text=value, font=("Segoe UI", 10, "bold"), fg=color, bg=BG2, anchor="w").pack(side="left")

    # ── Tokens ──

    def _show_tokens(self) -> None:
        self._clear_body()
        self._highlight_nav("Tokens")

        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=20)

        tk.Label(frame, text="Token Management", font=("Segoe UI", 14, "bold"), fg=TXT, bg=BG, anchor="w").pack(fill="x", pady=(0, 16))

        if not TOKENS_FILE.exists():
            tk.Label(frame, text="No tokens file found.", font=("Segoe UI", 10), fg=DANGER, bg=BG).pack(anchor="w")
            return

        try:
            tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
        except Exception:
            tk.Label(frame, text="Invalid tokens file.", font=("Segoe UI", 10), fg=DANGER, bg=BG).pack(anchor="w")
            return

        if not tokens:
            tk.Label(frame, text="No tokens stored.", font=("Segoe UI", 10), fg=MUTED, bg=BG).pack(anchor="w")
            return

        tk.Label(frame, text=f"Stored Tokens ({len(tokens)}):", font=("Segoe UI", 10, "bold"), fg=PRIMARY, bg=BG, anchor="w").pack(fill="x", pady=(0, 8))

        # Token list with scrollbar
        list_frame = tk.Frame(frame, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        list_frame.pack(fill="both", expand=True)

        for i, token in enumerate(tokens, 1):
            row = tk.Frame(list_frame, bg=BG2)
            row.pack(fill="x", padx=12, pady=4)
            tk.Label(row, text=f"{i}.", font=("Consolas", 10), fg=MUTED, bg=BG2, width=4, anchor="w").pack(side="left")
            tk.Label(row, text=token, font=("Consolas", 10), fg=PRIMARY, bg=BG2, anchor="w").pack(side="left")

        # Revoke section
        revoke_frame = tk.Frame(frame, bg=BG)
        revoke_frame.pack(fill="x", pady=(16, 0))

        tk.Label(revoke_frame, text="Revoke Token:", font=("Segoe UI", 10), fg=TXT2, bg=BG).pack(side="left", padx=(0, 8))
        self._revoke_var = tk.StringVar()
        tk.Entry(
            revoke_frame, textvariable=self._revoke_var, font=("Consolas", 10),
            bg=BG3, fg=TXT, relief="flat", width=30,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=DANGER,
        ).pack(side="left", padx=(0, 8), ipady=4)

        def _revoke():
            token = self._revoke_var.get().strip()
            if not token:
                return
            if token in tokens:
                tokens.remove(token)
                TOKENS_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
                messagebox.showinfo("KLATOM", f"Token revoked.\nRemaining: {len(tokens)}")
                self._show_tokens()
            else:
                messagebox.showwarning("KLATOM", "Token not found.")

        self._make_button(revoke_frame, "Revoke", DANGER, _revoke, fg="#fff", bg=DANGER, hover_bg="#CC3A30").pack(side="left")

    # ── Generate Tokens ──

    def _show_generate(self) -> None:
        self._clear_body()
        self._highlight_nav("Generate")

        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=20)

        tk.Label(frame, text="Generate Tokens", font=("Segoe UI", 14, "bold"), fg=TXT, bg=BG, anchor="w").pack(fill="x", pady=(0, 16))

        # Count input
        row = tk.Frame(frame, bg=BG)
        row.pack(fill="x", pady=(0, 16))
        tk.Label(row, text="Number of tokens:", font=("Segoe UI", 10), fg=TXT2, bg=BG).pack(side="left", padx=(0, 8))
        self._gen_count_var = tk.StringVar(value="1")
        tk.Entry(
            row, textvariable=self._gen_count_var, font=("Consolas", 10),
            bg=BG3, fg=TXT, relief="flat", width=8,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=PRIMARY,
        ).pack(side="left", ipady=4)

        # Generated tokens display
        self._gen_display = tk.Text(
            frame, height=12, font=("Consolas", 10),
            bg=BG3, fg=PRIMARY, relief="flat", state="disabled",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self._gen_display.pack(fill="both", expand=True, pady=(0, 16))

        def _generate():
            try:
                count = int(self._gen_count_var.get())
            except ValueError:
                count = 1
            if count < 1:
                count = 1

            from crypto import generate_token as _gen

            # Load existing tokens
            existing = []
            if TOKENS_FILE.exists():
                try:
                    existing = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
                except Exception:
                    existing = []

            new_tokens = []
            for _ in range(count):
                tok = _gen()
                new_tokens.append(tok)
                existing.append(tok)

            TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOKENS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")

            # Display
            self._gen_display.configure(state="normal")
            self._gen_display.delete("1.0", "end")
            self._gen_display.insert("1.0", f"Generated {count} token(s):\n\n")
            for t in new_tokens:
                self._gen_display.insert("end", f"  {t}\n")
            self._gen_display.insert("end", f"\nTotal: {len(existing)}")
            self._gen_display.configure(state="disabled")

        self._make_button(frame, "Generate", PRIMARY, _generate).pack(anchor="w")

    # ── Speed Test ──

    def _show_speed_test(self) -> None:
        self._clear_body()
        self._highlight_nav("Speed Test")

        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=20)

        tk.Label(frame, text="Proxy Speed Test", font=("Segoe UI", 14, "bold"), fg=TXT, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))
        tk.Label(frame, text="Test proxies from data/proxies.txt", font=("Segoe UI", 9), fg=MUTED, bg=BG, anchor="w").pack(fill="x", pady=(0, 16))

        proxy_file = DATA_DIR / "proxies.txt"
        if not proxy_file.exists():
            tk.Label(frame, text="No proxies.txt found.", font=("Segoe UI", 10), fg=DANGER, bg=BG).pack(anchor="w")
            return

        proxies = [p.strip() for p in proxy_file.read_text(encoding="utf-8").splitlines() if p.strip()]
        tk.Label(frame, text=f"{len(proxies)} proxies loaded", font=("Segoe UI", 10), fg=TXT2, bg=BG, anchor="w").pack(fill="x", pady=(0, 12))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Purple.Horizontal.TProgressbar", troughcolor=BG3, background=PRIMARY)

        self._speed_progress = ttk.Progressbar(frame, style="Purple.Horizontal.TProgressbar", length=400, mode="determinate")
        self._speed_progress.pack(fill="x", pady=(0, 8))

        self._speed_label = tk.Label(frame, text="Ready", font=("Segoe UI", 10), fg=MUTED, bg=BG)
        self._speed_label.pack(fill="x", pady=(0, 8))

        # Results
        self._speed_results = tk.Text(
            frame, height=10, font=("Consolas", 9),
            bg=BG3, fg=MUTED, relief="flat", state="disabled",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self._speed_results.pack(fill="both", expand=True, pady=(0, 12))

        def _run():
            from config import ENDPOINT
            import aiohttp

            self._speed_label.configure(text="Testing...", fg=PRIMARY)

            sem = asyncio.Semaphore(200)
            results = []
            tested = [0]
            lock = asyncio.Lock()

            async def _test_one(sess, proxy_raw):
                proxy = proxy_raw.strip()
                if not proxy.startswith("http"):
                    proxy = f"http://{proxy}"
                try:
                    start = time.time()
                    async with sess.post(ENDPOINT, json={"username": "a"}, proxy=proxy,
                                         headers={"Content-Type": "application/json"}) as resp:
                        if resp.status in (200, 201, 204, 400, 429):
                            latency = time.time() - start
                            async with lock:
                                results.append((proxy_raw, latency, resp.status))
                except Exception:
                    pass
                async with lock:
                    tested[0] += 1
                if tested[0] % 100 == 0 or tested[0] == len(proxies):
                    pct = tested[0] / max(len(proxies), 1) * 100
                    self.after(0, lambda t=tested[0], p=pct: (
                        self._speed_progress.configure(value=p),
                        self._speed_label.configure(text=f"{t}/{len(proxies)} ({p:.0f}%)"),
                    ))

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            connector = aiohttp.TCPConnector(limit=200, limit_per_host=0, ttl_dns_cache=300)

            async def _run_all():
                async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=5), trust_env=False) as sess:
                    tasks = [_test_one(sess, p) for p in proxies]
                    await asyncio.gather(*tasks)

            loop.run_until_complete(_run_all())
            loop.close()

            results.sort(key=lambda x: x[1])

            def _show():
                self._speed_progress.configure(value=100)
                self._speed_label.configure(text=f"Done: {len(results)}/{len(proxies)} alive", fg=SUCCESS if results else DANGER)

                self._speed_results.configure(state="normal")
                self._speed_results.delete("1.0", "end")
                self._speed_results.insert("1.0", f"{'#':<4} {'Proxy':<35} {'Latency':<10} {'Status'}\n")
                self._speed_results.insert("end", "─" * 65 + "\n")
                for i, (proxy, lat, status) in enumerate(results[:30], 1):
                    color = "green" if lat < 1 else "orange" if lat < 3 else "red"
                    self._speed_results.insert("end", f"{i:<4} {proxy:<35} {lat:.2f}s{' ':<4} {status}\n")
                if len(results) > 30:
                    self._speed_results.insert("end", f"\n...and {len(results) - 30} more")
                self._speed_results.configure(state="disabled")

                # Save fast proxies
                fast = [p for p, _, _ in results]
                fast_file = DATA_DIR / "proxies_fast.txt"
                fast_file.write_text("\n".join(fast), encoding="utf-8")

            self.after(0, _show)

        self._make_button(frame, "Start Test", PRIMARY, lambda: threading.Thread(target=_run, daemon=True).start()).pack(anchor="w")

    # ── Hits ──

    def _show_hits(self) -> None:
        self._clear_body()
        self._highlight_nav("Hits")

        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=20)

        tk.Label(frame, text="Available Usernames", font=("Segoe UI", 14, "bold"), fg=TXT, bg=BG, anchor="w").pack(fill="x", pady=(0, 16))

        hits_file = RESULTS_DIR / "hits.txt"
        if not hits_file.exists():
            tk.Label(frame, text="No hits file found.", font=("Segoe UI", 10), fg=DANGER, bg=BG).pack(anchor="w")
            return

        hits = [l.strip() for l in hits_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not hits:
            tk.Label(frame, text="No hits yet.", font=("Segoe UI", 10), fg=MUTED, bg=BG).pack(anchor="w")
            return

        tk.Label(frame, text=f"Found {len(hits)} available usernames:", font=("Segoe UI", 10, "bold"), fg=SUCCESS, bg=BG, anchor="w").pack(fill="x", pady=(0, 8))

        text = tk.Text(
            frame, font=("Consolas", 10), bg=BG3, fg=SUCCESS, relief="flat",
            state="disabled", highlightthickness=1, highlightbackground=BORDER,
        )
        text.pack(fill="both", expand=True)
        text.configure(state="normal")
        for i, h in enumerate(hits[:100], 1):
            text.insert("end", f"  {i}. {h}\n")
        if len(hits) > 100:
            text.insert("end", f"\n  ...and {len(hits) - 100} more")
        text.configure(state="disabled")

    # ── Clear Auth ──

    def _show_clear_auth(self) -> None:
        self._clear_body()
        self._highlight_nav("Clear Auth")

        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=20)

        tk.Label(frame, text="Clear All Auth Data", font=("Segoe UI", 14, "bold"), fg=DANGER, bg=BG, anchor="w").pack(fill="x", pady=(0, 8))
        tk.Label(frame, text="This will delete all tokens, sessions, and auth data.", font=("Segoe UI", 10), fg=WARNING, bg=BG, anchor="w").pack(fill="x", pady=(0, 24))

        tk.Label(frame, text="Affected files:", font=("Segoe UI", 10, "bold"), fg=TXT2, bg=BG, anchor="w").pack(fill="x")
        for f in [AUTH_FILE, SESSION_FILE, TOKENS_FILE]:
            status = "Exists" if f.exists() else "Not found"
            color = WARNING if f.exists() else MUTED
            tk.Label(frame, text=f"  {f.name}: {status}", font=("Consolas", 10), fg=color, bg=BG, anchor="w").pack(fill="x")

        def _clear():
            if not messagebox.askyesno("KLATOM", "Are you sure you want to delete ALL auth data?"):
                return
            for f in [AUTH_FILE, SESSION_FILE]:
                if f.exists():
                    f.unlink()
            if TOKENS_FILE.exists():
                TOKENS_FILE.write_text("[]", encoding="utf-8")
            messagebox.showinfo("KLATOM", "All auth data cleared.")
            self._show_session()

        self._make_button(frame, "Clear All Auth", DANGER, _clear, fg="#fff", bg=DANGER, hover_bg="#CC3A30").pack(anchor="w", pady=(24, 0))

    # ── Helpers ──

    def _make_button(self, parent, text, bg, command, fg="#fff", hover_bg=None, **kwargs) -> tk.Button:
        btn = tk.Button(
            parent, text=text, command=command,
            font=("Segoe UI", 10, "bold"), fg=fg, bg=bg,
            activebackground=hover_bg or bg, activeforeground=fg,
            relief="flat", cursor="hand2", padx=16, pady=8, **kwargs,
        )

        def _enter(e):
            if hover_bg:
                btn.configure(bg=hover_bg)
        def _leave(e):
            btn.configure(bg=bg)

        btn.bind("<Enter>", _enter)
        btn.bind("<Leave>", _leave)
        return btn


def main() -> None:
    app = ModApp()
    app.mainloop()


if __name__ == "__main__":
    main()
