#!/usr/bin/env python3
"""KLATOM v3.3 - Modern tkinter GUI."""

from __future__ import annotations

import asyncio
import itertools
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Any

from config import (
    DATA_DIR, LOGS_DIR, RESULTS_DIR, VERSION,
    AppSettings, Config, RunConfig, Stats,
    ensure_dir, ensure_file, load_lines, is_valid_username, USERNAME_CHARS, MAX_CONCURRENCY,
    C as Colors,
)

# ── Color Palette ──

BG = "#0C0C12"
BG2 = "#15151E"
BG3 = "#1C1C28"
BORDER = "#2A2A35"
TXT = "#F0F0F5"
TXT2 = "#8888A0"
MUTED = "#7A7A82"
PRIMARY = "#A855F7"
PRIMARY_D = "#7C3AED"
PRIMARY_L = "#C084FC"
SUCCESS = "#30D158"
DANGER = "#FF453A"
WARNING = "#FF9F0A"


class App(tk.Tk):
    """KLATOM main GUI application."""

    def __init__(self) -> None:
        super().__init__()
        self.title("KLATOM v" + VERSION)
        self.geometry("720x580")
        self.minsize(640, 500)
        self.configure(bg=BG)
        self.resizable(True, True)

        # Center window
        self.update_idletasks()
        w, h = 720, 580
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        # State
        self.config = Config()
        self._async_loop: asyncio.AbstractEventLoop | None = None
        self._async_thread: threading.Thread | None = None

        # Build UI
        self._build_header()
        self._build_body()
        self._show_auth_screen()

        # Start async loop in background thread
        self._start_async_loop()

    def _start_async_loop(self) -> None:
        self._async_loop = asyncio.new_event_loop()

        def _run():
            asyncio.set_event_loop(self._async_loop)
            self._async_loop.run_forever()

        self._async_thread = threading.Thread(target=_run, daemon=True)
        self._async_thread.start()

    def _run_async(self, coro) -> asyncio.Future:
        return asyncio.run_coroutine_threadsafe(coro, self._async_loop)

    # ── Header ──

    def _build_header(self) -> None:
        self._header = tk.Frame(self, bg=BG2, height=56)
        self._header.pack(fill="x", side="top")
        self._header.pack_propagate(False)

        # Title
        title_frame = tk.Frame(self._header, bg=BG2)
        title_frame.pack(side="left", padx=20, pady=10)

        tk.Label(
            title_frame, text="KL", font=("Segoe UI", 18, "bold"),
            fg=PRIMARY, bg=BG2,
        ).pack(side="left")
        tk.Label(
            title_frame, text="ATOM", font=("Segoe UI", 18, "bold"),
            fg=TXT, bg=BG2,
        ).pack(side="left")
        tk.Label(
            title_frame, text=f"  v{VERSION}", font=("Segoe UI", 10),
            fg=MUTED, bg=BG2,
        ).pack(side="left", padx=(8, 0))

        # Status badge
        self._status_label = tk.Label(
            self._header, text="  Ready  ", font=("Segoe UI", 9),
            fg=SUCCESS, bg=BG3, padx=8, pady=2,
        )
        self._status_label.pack(side="right", padx=20)

    # ── Body ──

    def _build_body(self) -> None:
        self._body = tk.Frame(self, bg=BG)
        self._body.pack(fill="both", expand=True, padx=0, pady=0)

    def _clear_body(self) -> None:
        for w in self._body.winfo_children():
            w.destroy()

    # ── Auth Screen ──

    def _show_auth_screen(self) -> None:
        self._clear_body()
        self._status_label.configure(text="  Auth  ", fg=WARNING)

        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=40, pady=30)

        # Welcome
        tk.Label(
            frame, text="Welcome to KLATOM", font=("Segoe UI", 16, "bold"),
            fg=PRIMARY, bg=BG,
        ).pack(pady=(0, 6))
        tk.Label(
            frame, text="License authentication required", font=("Segoe UI", 10),
            fg=MUTED, bg=BG,
        ).pack(pady=(0, 24))

        # Token entry
        tk.Label(
            frame, text="License Token", font=("Segoe UI", 10, "bold"),
            fg=TXT2, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 6))

        self._token_var = tk.StringVar()
        self._token_entry = tk.Entry(
            frame, textvariable=self._token_var,
            font=("Consolas", 11), bg=BG3, fg=TXT,
            insertbackground=PRIMARY, relief="flat",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=PRIMARY,
        )
        self._token_entry.pack(fill="x", ipady=8, pady=(0, 16))
        self._token_entry.bind("<Return>", lambda e: self._submit_token())

        # Buttons
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill="x", pady=(0, 12))

        self._make_button(
            btn_frame, "Activate License", PRIMARY, self._submit_token,
        ).pack(side="left", padx=(0, 10))

        self._make_button(
            btn_frame, "Start Free Trial (24h)", BG3, self._start_trial,
            fg=WARNING, bg=BG3, hover_bg=BORDER,
        ).pack(side="left", padx=(0, 10))

        # Message
        self._auth_msg = tk.Label(
            frame, text="", font=("Segoe UI", 9), fg=DANGER, bg=BG, wraplength=400,
        )
        self._auth_msg.pack(pady=(12, 0))

        # Check existing auth
        self._check_existing_auth()

    def _check_existing_auth(self) -> None:
        from crypto import load_auth, hash_token, token_in_store
        auth_file = DATA_DIR / ".auth"

        # Check session (trial)
        session_file = DATA_DIR / ".session"
        if session_file.exists():
            try:
                from crypto import load_session
                data = load_session(session_file)
                if data:
                    import time as _time
                    start = data.get("ts", 0)
                    hwid = data.get("th", "")
                    from crypto import get_hwid
                    if start and (not hwid or hwid == get_hwid()):
                        if (_time.time() - start) < 86400:
                            self._auth_msg.configure(text="Trial session active", fg=SUCCESS)
                            self.after(800, self._show_wizard_screen)
                            return
            except Exception:
                pass

        # Check CREATOR in auth
        if auth_file.exists():
            try:
                from crypto import load_auth, hash_token
                data = load_auth(auth_file)
                if data and hash_token("CREATOR") in data.get("t", []):
                    self._auth_msg.configure(text="Creator access", fg=SUCCESS)
                    self.after(500, self._show_wizard_screen)
                    return
            except Exception:
                pass

    def _submit_token(self) -> None:
        token = self._token_var.get().strip()
        if not token:
            self._auth_msg.configure(text="Enter a license token", fg=DANGER)
            return

        from auth import is_token_approved, add_approved_token
        if is_token_approved(token):
            self._auth_msg.configure(text="Token approved", fg=SUCCESS)
            self.after(500, self._show_wizard_screen)
            return

        # First run: auto-approve
        auth_file = DATA_DIR / ".auth"
        from crypto import load_auth
        data = load_auth(auth_file)
        if data is None or not data.get("t"):
            add_approved_token("CREATOR")
            add_approved_token(token)
            self._auth_msg.configure(text="Creator token registered", fg=SUCCESS)
            self.after(500, self._show_wizard_screen)
            return

        self._auth_msg.configure(text="Invalid or expired token", fg=DANGER)

    def _start_trial(self) -> None:
        from auth import _activate_trial
        _activate_trial()
        self._auth_msg.configure(text="Free trial activated (24h)", fg=SUCCESS)
        self.after(500, self._show_wizard_screen)

    # ── Wizard Screen ──

    def _show_wizard_screen(self) -> None:
        self._clear_body()
        self._status_label.configure(text="  Setup  ", fg=PRIMARY)

        self._wizard_data = {
            "proxies": [],
            "scraped": False,
            "remove_bad": True,
            "usernames": [],
            "concurrency": 50,
            "timeout": 10,
            "webhook_url": None,
            "webhook_msg": None,
        }

        self._build_wizard_step(0)

    def _build_wizard_step(self, step: int) -> None:
        for w in self._body.winfo_children():
            w.destroy()

        # Progress bar
        self._build_step_progress(step)

        if step == 0:
            self._step_proxy_source()
        elif step == 1:
            self._step_speed_test()
        elif step == 2:
            self._step_usernames()
        elif step == 3:
            self._step_speed()
        elif step == 4:
            self._step_webhook()
        elif step == 5:
            self._step_summary()

    def _build_step_progress(self, current: int) -> None:
        pf = tk.Frame(self._body, bg=BG)
        pf.pack(fill="x", padx=30, pady=(16, 0))

        steps = ["Proxies", "Speed", "Usernames", "Speed", "Webhook"]
        for i, label in enumerate(steps):
            color = SUCCESS if i < current else PRIMARY if i == current else MUTED
            sep = tk.Label(pf, text=" \u2022 ", fg=BORDER, bg=BG, font=("Segoe UI", 9))
            if i > 0:
                sep.pack(side="left")
            tk.Label(
                pf, text=label, font=("Segoe UI", 9, "bold" if i == current else "normal"),
                fg=color, bg=BG,
            ).pack(side="left")

        # Separator line
        tk.Frame(self._body, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(12, 0))

    # ── Step 0: Proxy Source ──

    def _step_proxy_source(self) -> None:
        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=16)

        tk.Label(
            frame, text="Proxy Source", font=("Segoe UI", 14, "bold"),
            fg=TXT, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 4))
        tk.Label(
            frame, text="Proxies are strongly recommended to avoid rate-limiting",
            font=("Segoe UI", 9), fg=MUTED, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 16))

        # Source selection
        self._proxy_source_var = tk.StringVar(value="file")

        for val, label, desc in [
            ("file", "From File", "Load proxies from a text file"),
            ("paste", "Paste", "Paste proxies directly"),
            ("scrape", "Scrape Free", "Auto-fetch from public sources"),
            ("none", "None", "Run without proxies (rate-limited)"),
        ]:
            rf = tk.Frame(frame, bg=BG)
            rf.pack(fill="x", pady=3)
            tk.Radiobutton(
                rf, variable=self._proxy_source_var, value=val,
                bg=BG, fg=PRIMARY, selectcolor=BG3, activebackground=BG,
                activeforeground=PRIMARY, font=("Segoe UI", 10),
            ).pack(side="left")
            tk.Label(
                rf, text=label, font=("Segoe UI", 10, "bold"),
                fg=TXT, bg=BG,
            ).pack(side="left", padx=(4, 8))
            tk.Label(
                rf, text=desc, font=("Segoe UI", 9),
                fg=MUTED, bg=BG,
            ).pack(side="left")

        # File path (shown when file is selected)
        self._proxy_file_frame = tk.Frame(frame, bg=BG)
        self._proxy_file_frame.pack(fill="x", pady=(16, 0))

        tk.Label(
            self._proxy_file_frame, text="Proxy File", font=("Segoe UI", 10, "bold"),
            fg=TXT2, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 6))

        path_row = tk.Frame(self._proxy_file_frame, bg=BG)
        path_row.pack(fill="x")

        default_path = str(DATA_DIR / "proxies.txt")
        self._proxy_path_var = tk.StringVar(value=default_path)
        self._proxy_path_entry = tk.Entry(
            path_row, textvariable=self._proxy_path_var,
            font=("Consolas", 10), bg=BG3, fg=TXT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=PRIMARY,
        )
        self._proxy_path_entry.pack(side="left", fill="x", expand=True, ipady=6)

        self._make_button(
            path_row, "Browse", BG3, self._browse_proxy_file,
            fg=TXT, bg=BG3, hover_bg=BORDER, width=8,
        ).pack(side="right", padx=(8, 0))

        # Auto-remove checkbox
        self._remove_bad_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            frame, text="Auto-remove dead proxies",
            variable=self._remove_bad_var,
            bg=BG, fg=TXT2, selectcolor=BG3, activebackground=BG,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(16, 0))

        # Paste text area (hidden by default)
        self._paste_frame = tk.Frame(frame, bg=BG)
        tk.Label(
            self._paste_frame, text="Paste proxies (one per line):",
            font=("Segoe UI", 10, "bold"), fg=TXT2, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 6))
        self._paste_text = tk.Text(
            self._paste_frame, height=6, font=("Consolas", 10),
            bg=BG3, fg=TXT, insertbackground=PRIMARY, relief="flat",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self._paste_text.pack(fill="x")

        # Bind radio change
        self._proxy_source_var.trace_add("write", self._on_proxy_source_change)

        # Buttons
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill="x", pady=(20, 0))
        self._make_button(
            btn_frame, "Next  \u2192", PRIMARY, self._finish_proxy_step,
        ).pack(side="right")

    def _on_proxy_source_change(self, *_args) -> None:
        src = self._proxy_source_var.get()
        if src == "file":
            self._proxy_file_frame.pack(fill="x", pady=(16, 0))
            self._paste_frame.pack_forget()
        elif src == "paste":
            self._proxy_file_frame.pack_forget()
            self._paste_frame.pack(fill="x", pady=(16, 0))
        else:
            self._proxy_file_frame.pack_forget()
            self._paste_frame.pack_forget()

    def _browse_proxy_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            self._proxy_path_var.set(path)

    def _finish_proxy_step(self) -> None:
        src = self._proxy_source_var.get()
        if src == "file":
            proxies = load_lines(self._proxy_path_var.get())
        elif src == "paste":
            raw = self._paste_text.get("1.0", "end")
            proxies = [l.strip() for l in raw.splitlines() if l.strip()]
        elif src == "scrape":
            proxies = []  # Will be filled by async scrape
            self._wizard_data["scraped"] = True
        else:
            proxies = []

        self._wizard_data["proxies"] = proxies
        self._wizard_data["remove_bad"] = self._remove_bad_var.get()

        if src == "scrape":
            self._show_scraping_screen()
        else:
            self._build_wizard_step(1 if proxies and len(proxies) > 10 and self._wizard_data["scraped"] else 2)

    def _show_scraping_screen(self) -> None:
        self._clear_body()
        self._status_label.configure(text="  Scraping  ", fg=WARNING)

        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=30)

        tk.Label(
            frame, text="Scraping Proxies...", font=("Segoe UI", 14, "bold"),
            fg=TXT, bg=BG,
        ).pack(pady=(0, 8))

        self._scrape_status = tk.Label(
            frame, text="Fetching from public sources...", font=("Segoe UI", 10),
            fg=MUTED, bg=BG,
        )
        self._scrape_status.pack(pady=(0, 16))

        # Progress bar
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Purple.Horizontal.TProgressbar", troughcolor=BG3, background=PRIMARY)

        self._scrape_progress = ttk.Progressbar(
            frame, style="Purple.Horizontal.TProgressbar",
            length=400, mode="determinate",
        )
        self._scrape_progress.pack(pady=(0, 16))

        self._scrape_log = tk.Text(
            frame, height=10, font=("Consolas", 9),
            bg=BG3, fg=MUTED, relief="flat", state="disabled",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self._scrape_log.pack(fill="both", expand=True)

        # Run scraping in background
        def _do_scrape():
            import aiohttp
            import re as _re

            SOURCES = [
                ("TheSpeedX", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"),
                ("monosans", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"),
                ("proxifly", "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt"),
                ("ShiftyTR-http", "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt"),
                ("ShiftyTR-https", "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt"),
                ("sunny9577", "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt"),
                ("mmpx12-http", "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt"),
                ("mmpx12-https", "https://raw.githubusercontent.com/mmpx12/proxy-list/master/https.txt"),
                ("proxyscrape.com", "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"),
            ]

            proxy_re = re.compile(
                r"^(?:https?://)?[a-zA-Z0-9](?:[a-zA-Z0-9\-.]*[a-zA-Z0-9])?:\d{1,5}$"
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def _fetch(name, url):
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10), trust_env=False) as s:
                        async with s.get(url) as r:
                            if r.status != 200:
                                return name, [], f"HTTP {r.status}"
                            text = await r.text()
                            found = [p.strip() for p in text.splitlines() if proxy_re.match(p.strip())]
                            return name, found, "ok"
                except Exception as e:
                    return name, [], str(e)

            async def _run_all():
                tasks = [_fetch(n, u) for n, u in SOURCES]
                return await asyncio.gather(*tasks)

            results = loop.run_until_complete(_run_all())
            loop.close()

            seen = set()
            all_proxies = []
            for name, batch, status in results:
                self.after(0, lambda n=name, b=batch, s=status:
                    self._append_scrape_log(f"{'+' if s == 'ok' else 'x'} {n}: {len(b)} proxies ({s})"))
                for p in batch:
                    key = p.split("@")[-1] if "@" in p else p
                    if key not in seen:
                        seen.add(key)
                        all_proxies.append(p)

            self._wizard_data["proxies"] = all_proxies
            self._wizard_data["scraped"] = True

            self.after(0, lambda: self._scrape_status.configure(
                text=f"Done: {len(all_proxies)} unique proxies found", fg=SUCCESS
            ))
            self.after(0, lambda: self._scrape_progress.configure(value=100))
            self.after(1500, lambda: self._build_wizard_step(
                1 if len(all_proxies) > 10 else 2
            ))

        threading.Thread(target=_do_scrape, daemon=True).start()

    def _append_scrape_log(self, msg: str) -> None:
        self._scrape_log.configure(state="normal")
        self._scrape_log.insert("end", msg + "\n")
        self._scrape_log.see("end")
        self._scrape_log.configure(state="disabled")
        # Update progress
        lines = int(self._scrape_log.index("end-1c").split(".")[0])
        self._scrape_progress.configure(value=min(lines / 9 * 100, 100))

    # ── Step 1: Speed Test ──

    def _step_speed_test(self) -> None:
        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=16)

        proxies = self._wizard_data["proxies"]
        tk.Label(
            frame, text="Speed Test", font=("Segoe UI", 14, "bold"),
            fg=TXT, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 4))
        tk.Label(
            frame, text=f"Test {len(proxies)} scraped proxies for latency and availability",
            font=("Segoe UI", 9), fg=MUTED, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 16))

        style = ttk.Style()
        style.configure("Purple.Horizontal.TProgressbar", troughcolor=BG3, background=PRIMARY)

        self._speed_progress = ttk.Progressbar(
            frame, style="Purple.Horizontal.TProgressbar",
            length=400, mode="determinate",
        )
        self._speed_progress.pack(pady=(0, 8))

        self._speed_label = tk.Label(
            frame, text="Ready to test", font=("Segoe UI", 10), fg=MUTED, bg=BG,
        )
        self._speed_label.pack(pady=(0, 16))

        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill="x")
        self._make_button(
            btn_frame, "Start Speed Test", PRIMARY, self._run_speed_test,
        ).pack(side="left", padx=(0, 10))
        self._make_button(
            btn_frame, "Skip", BG3, lambda: self._build_wizard_step(2),
            fg=TXT, bg=BG3, hover_bg=BORDER,
        ).pack(side="left")

    def _run_speed_test(self) -> None:
        self._speed_label.configure(text="Testing...", fg=PRIMARY)

        def _do_test():
            from proxy import ProxyManager

            proxies = self._wizard_data["proxies"]
            pm = ProxyManager(proxies, remove_on_fail=True, scored=True)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            def _on_progress(tested, total, working):
                pct = tested / max(total, 1) * 100
                self.after(0, lambda t=tested, tt=total, w=working, p=pct: (
                    self._speed_progress.configure(value=p),
                    self._speed_label.configure(
                        text=f"{t}/{tt} tested — {w} working ({p:.0f}%)", fg=TXT
                    ),
                ))

            results = loop.run_until_complete(pm.speed_test(
                concurrency=200, timeout=8.0, on_progress=_on_progress,
            ))
            working = loop.run_until_complete(pm.apply_speed_results(
                results, remove_slow=True, max_latency_ms=3000,
            ))
            loop.close()

            working_proxies = [r[0] for r in results if r[2] and r[1] < 3000]
            self._wizard_data["proxies"] = working_proxies

            self.after(0, lambda: (
                self._speed_progress.configure(value=100),
                self._speed_label.configure(
                    text=f"Done: {working} working proxies (of {len(proxies)})",
                    fg=SUCCESS if working > 0 else DANGER,
                ),
            ))
            self.after(1000, lambda: self._build_wizard_step(2))

        threading.Thread(target=_do_test, daemon=True).start()

    # ── Step 2: Usernames ──

    def _step_usernames(self) -> None:
        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=16)

        tk.Label(
            frame, text="Usernames", font=("Segoe UI", 14, "bold"),
            fg=TXT, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 16))

        # Source selection
        self._names_source_var = tk.StringVar(value="file")

        for val, label in [("file", "Load from File"), ("generate", "Generate Random")]:
            rf = tk.Frame(frame, bg=BG)
            rf.pack(fill="x", pady=3)
            tk.Radiobutton(
                rf, variable=self._names_source_var, value=val,
                bg=BG, fg=PRIMARY, selectcolor=BG3, activebackground=BG,
                font=("Segoe UI", 10),
            ).pack(side="left")
            tk.Label(
                rf, text=label, font=("Segoe UI", 10), fg=TXT, bg=BG,
            ).pack(side="left", padx=(4, 0))

        # File path
        self._names_file_frame = tk.Frame(frame, bg=BG)
        self._names_file_frame.pack(fill="x", pady=(12, 0))

        path_row = tk.Frame(self._names_file_frame, bg=BG)
        path_row.pack(fill="x")

        default_names = str(DATA_DIR / "names_to_check.txt")
        self._names_path_var = tk.StringVar(value=default_names)
        self._names_path_entry = tk.Entry(
            path_row, textvariable=self._names_path_var,
            font=("Consolas", 10), bg=BG3, fg=TXT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=PRIMARY,
        )
        self._names_path_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self._make_button(
            path_row, "Browse", BG3, self._browse_names_file,
            fg=TXT, bg=BG3, hover_bg=BORDER, width=8,
        ).pack(side="right", padx=(8, 0))

        # Generate options (hidden by default)
        self._names_gen_frame = tk.Frame(frame, bg=BG)
        tk.Label(
            self._names_gen_frame, text="Username length:", font=("Segoe UI", 10),
            fg=TXT2, bg=BG,
        ).pack(side="left", padx=(0, 8))
        self._names_len_var = tk.StringVar(value="4")
        for length in ["3", "4", "5"]:
            tk.Radiobutton(
                self._names_gen_frame, variable=self._names_len_var, value=length,
                text=f"{length} chars", bg=BG, fg=TXT, selectcolor=BG3,
                activebackground=BG, font=("Segoe UI", 10),
            ).pack(side="left", padx=(0, 8))

        self._names_source_var.trace_add("write", self._on_names_source_change)

        # Buttons
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill="x", pady=(20, 0))
        self._make_button(
            btn_frame, "Next  \u2192", PRIMARY, self._finish_names_step,
        ).pack(side="right")

    def _on_names_source_change(self, *_args) -> None:
        if self._names_source_var.get() == "file":
            self._names_file_frame.pack(fill="x", pady=(12, 0))
            self._names_gen_frame.pack_forget()
        else:
            self._names_file_frame.pack_forget()
            self._names_gen_frame.pack(fill="x", pady=(12, 0))

    def _browse_names_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            self._names_path_var.set(path)

    def _finish_names_step(self) -> None:
        if self._names_source_var.get() == "file":
            usernames = load_lines(self._names_path_var.get())
        else:
            import itertools as _it
            import random as _rand
            length = int(self._names_len_var.get())
            chars = USERNAME_CHARS
            if length >= 5:
                seen = set()
                usernames = []
                while len(usernames) < 50000:
                    cand = "".join(_rand.choices(chars, k=length))
                    if cand not in seen and is_valid_username(cand):
                        seen.add(cand)
                        usernames.append(cand)
            else:
                combos = ["".join(c) for c in _it.product(chars, repeat=length)]
                usernames = [c for c in combos if is_valid_username(c)]
                usernames = _rand.sample(usernames, min(50000, len(usernames)))

        if not usernames:
            messagebox.showwarning("KLATOM", "No usernames found or generated.")
            return

        self._wizard_data["usernames"] = usernames
        self._build_wizard_step(3)

    # ── Step 3: Speed Settings ──

    def _step_speed(self) -> None:
        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=16)

        tk.Label(
            frame, text="Performance", font=("Segoe UI", 14, "bold"),
            fg=TXT, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 16))

        proxies = self._wizard_data["proxies"]
        scraped = self._wizard_data["scraped"]

        # Concurrency
        tk.Label(
            frame, text="Concurrent Workers", font=("Segoe UI", 10, "bold"),
            fg=TXT2, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 6))

        if scraped:
            default_conc = 100
        elif proxies:
            default_conc = min(MAX_CONCURRENCY, max(10, len(proxies) * 5))
        else:
            default_conc = 1

        self._conc_var = tk.IntVar(value=default_conc)
        conc_scale = tk.Scale(
            frame, variable=self._conc_var, from_=1, to=min(2000, MAX_CONCURRENCY),
            orient="horizontal", bg=BG, fg=TXT, troughcolor=BG3,
            highlightthickness=0, font=("Segoe UI", 9),
            length=400,
        )
        conc_scale.pack(fill="x", pady=(0, 16))

        # Timeout
        tk.Label(
            frame, text="Request Timeout (seconds)", font=("Segoe UI", 10, "bold"),
            fg=TXT2, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 6))

        default_timeout = 5 if scraped else 10
        self._timeout_var = tk.IntVar(value=default_timeout)
        timeout_scale = tk.Scale(
            frame, variable=self._timeout_var, from_=1, to=30,
            orient="horizontal", bg=BG, fg=TXT, troughcolor=BG3,
            highlightthickness=0, font=("Segoe UI", 9),
            length=400,
        )
        timeout_scale.pack(fill="x", pady=(0, 16))

        # Info
        if not proxies:
            tk.Label(
                frame, text="Proxyless mode: 1 worker with delay",
                font=("Segoe UI", 9), fg=WARNING, bg=BG,
            ).pack(anchor="w")

        # Buttons
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill="x", pady=(16, 0))
        self._make_button(
            btn_frame, "Next  \u2192", PRIMARY, self._finish_speed_step,
        ).pack(side="right")

    def _finish_speed_step(self) -> None:
        self._wizard_data["concurrency"] = self._conc_var.get()
        self._wizard_data["timeout"] = self._timeout_var.get()
        self._build_wizard_step(4)

    # ── Step 4: Webhook ──

    def _step_webhook(self) -> None:
        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=16)

        tk.Label(
            frame, text="Discord Webhook", font=("Segoe UI", 14, "bold"),
            fg=TXT, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 4))
        tk.Label(
            frame, text="Optional: get notified when usernames are found",
            font=("Segoe UI", 9), fg=MUTED, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 16))

        # Enable webhook
        self._webhook_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            frame, text="Send hits to Discord webhook",
            variable=self._webhook_var,
            bg=BG, fg=TXT2, selectcolor=BG3, activebackground=BG,
            font=("Segoe UI", 10),
            command=self._toggle_webhook_fields,
        ).pack(anchor="w", pady=(0, 12))

        # Webhook fields
        self._webhook_fields = tk.Frame(frame, bg=BG)

        tk.Label(
            self._webhook_fields, text="Webhook URL", font=("Segoe UI", 10, "bold"),
            fg=TXT2, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 6))
        self._webhook_url_var = tk.StringVar()
        tk.Entry(
            self._webhook_fields, textvariable=self._webhook_url_var,
            font=("Consolas", 10), bg=BG3, fg=TXT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=PRIMARY,
        ).pack(fill="x", ipady=6, pady=(0, 12))

        tk.Label(
            self._webhook_fields, text="Message Template", font=("Segoe UI", 10, "bold"),
            fg=TXT2, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 6))
        tk.Label(
            self._webhook_fields, text="Use <name>, <time>, <elapsed> as placeholders",
            font=("Segoe UI", 9), fg=MUTED, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 4))
        self._webhook_msg_var = tk.StringVar(value="**<name>** available | <t:time:R>")
        tk.Entry(
            self._webhook_fields, textvariable=self._webhook_msg_var,
            font=("Consolas", 10), bg=BG3, fg=TXT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=PRIMARY,
        ).pack(fill="x", ipady=6)

        # Load saved webhook
        saved_url = self.config.get("webhook", "")
        if saved_url:
            self._webhook_var.set(True)
            self._webhook_url_var.set(saved_url)
            saved_msg = self.config.get("webhook_message", "**<name>** available | <t:time:R>")
            self._webhook_msg_var.set(saved_msg)
            self._webhook_fields.pack(fill="x")

        # Buttons
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill="x", pady=(20, 0))
        self._make_button(
            btn_frame, "Next  \u2192", PRIMARY, self._finish_webhook_step,
        ).pack(side="right")

    def _toggle_webhook_fields(self) -> None:
        if self._webhook_var.get():
            self._webhook_fields.pack(fill="x")
        else:
            self._webhook_fields.pack_forget()

    def _finish_webhook_step(self) -> None:
        if self._webhook_var.get():
            url = self._webhook_url_var.get().strip()
            msg = self._webhook_msg_var.get().strip()
            self._wizard_data["webhook_url"] = url or None
            self._wizard_data["webhook_msg"] = msg or None
            if url:
                self.config.set("webhook", url)
                self.config.set("webhook_message", msg)
        self._build_wizard_step(5)

    # ── Step 5: Summary & Start ──

    def _step_summary(self) -> None:
        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=16)

        tk.Label(
            frame, text="Ready to Start", font=("Segoe UI", 14, "bold"),
            fg=TXT, bg=BG, anchor="w",
        ).pack(fill="x", pady=(0, 16))

        # Config summary
        d = self._wizard_data
        summary_frame = tk.Frame(frame, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        summary_frame.pack(fill="x", pady=(0, 16))

        items = [
            ("Proxies", f"{len(d['proxies'])} {'(free/scraped)' if d['scraped'] else ''}"),
            ("Usernames", str(len(d["usernames"]))),
            ("Workers", str(d["concurrency"])),
            ("Timeout", f"{d['timeout']}s"),
            ("Webhook", "On" if d["webhook_url"] else "Off"),
        ]
        for label, value in items:
            row = tk.Frame(summary_frame, bg=BG2)
            row.pack(fill="x", padx=16, pady=6)
            tk.Label(row, text=label, font=("Segoe UI", 10), fg=MUTED, bg=BG2, width=12, anchor="w").pack(side="left")
            tk.Label(row, text=value, font=("Segoe UI", 10, "bold"), fg=TXT, bg=BG2, anchor="w").pack(side="left")

        # Start button
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill="x", pady=(16, 0))

        self._make_button(
            btn_frame, "Start Checking", SUCCESS, self._start_checking,
            fg="#fff", bg=SUCCESS, hover_bg="#28B84D",
        ).pack(side="right")

        self._make_button(
            btn_frame, "\u2190 Back", BG3, lambda: self._build_wizard_step(4),
            fg=TXT, bg=BG3, hover_bg=BORDER,
        ).pack(side="right", padx=(0, 10))

    def _start_checking(self) -> None:
        d = self._wizard_data
        if not d["usernames"]:
            messagebox.showwarning("KLATOM", "No usernames to check.")
            return

        run_config = RunConfig(
            proxies=d["proxies"],
            remove_bad_proxies=d["remove_bad"],
            usernames=d["usernames"],
            concurrency=d["concurrency"],
            timeout=d["timeout"],
            scraped=d["scraped"],
            webhook_url=d["webhook_url"],
            webhook_message=d["webhook_msg"],
        )

        self._show_checking_screen(run_config)

    # ── Checking Screen ──

    def _show_checking_screen(self, cfg: RunConfig) -> None:
        self._clear_body()
        self._status_label.configure(text="  Running  ", fg=SUCCESS)

        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=20, pady=16)

        # Progress bar
        style = ttk.Style()
        style.configure("Green.Horizontal.TProgressbar", troughcolor=BG3, background=SUCCESS)

        self._check_progress = ttk.Progressbar(
            frame, style="Green.Horizontal.TProgressbar",
            length=500, mode="determinate",
        )
        self._check_progress.pack(fill="x", pady=(0, 8))

        # Stats frame
        stats_frame = tk.Frame(frame, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        stats_frame.pack(fill="x", pady=(0, 8))

        self._stat_labels = {}
        for key, label, color in [
            ("available", "Available", SUCCESS),
            ("taken", "Taken", DANGER),
            ("reqs", "Requests", PRIMARY),
            ("rps", "Req/s", PRIMARY),
            ("errors", "Errors", DANGER),
            ("elapsed", "Elapsed", MUTED),
        ]:
            row = tk.Frame(stats_frame, bg=BG2)
            row.pack(fill="x", padx=12, pady=4)
            tk.Label(row, text=label, font=("Segoe UI", 10), fg=MUTED, bg=BG2, width=10, anchor="w").pack(side="left")
            lbl = tk.Label(row, text="0", font=("Segoe UI", 10, "bold"), fg=color, bg=BG2, anchor="w")
            lbl.pack(side="left")
            self._stat_labels[key] = lbl

        # Feed
        tk.Label(
            frame, text="Activity", font=("Segoe UI", 10, "bold"),
            fg=TXT2, bg=BG, anchor="w",
        ).pack(fill="x", pady=(8, 4))

        self._feed_text = tk.Text(
            frame, height=12, font=("Consolas", 9),
            bg=BG3, fg=MUTED, relief="flat", state="disabled",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self._feed_text.pack(fill="both", expand=True)

        # Stop button
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill="x", pady=(8, 0))
        self._stop_event = threading.Event()
        self._make_button(
            btn_frame, "Stop", DANGER, self._stop_checking,
            fg="#fff", bg=DANGER, hover_bg="#CC3A30",
        ).pack(side="right")

        # Start checking in background
        threading.Thread(target=self._run_checking, args=(cfg,), daemon=True).start()

    def _run_checking(self, cfg: RunConfig) -> None:
        import aiohttp
        from proxy import ProxyManager
        from engine import Checker, CircuitBreaker, WebhookSender, set_debug
        from config import ENDPOINT

        set_debug(False)

        pm = ProxyManager(cfg.proxies, remove_on_fail=cfg.remove_bad_proxies, scored=cfg.scraped)
        stats = Stats()
        start_time = time.time()

        names = list(cfg.usernames)
        total = len(names)
        _idx = [0]
        _lock = asyncio.Lock()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _next_task():
            async with _lock:
                if _idx[0] >= total:
                    return None
                i = _idx[0]
                _idx[0] += 1
            return i, names[i]

        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENCY * 2, limit_per_host=0, ttl_dns_cache=300)
        session_timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=30)

        async def _run():
            session = aiohttp.ClientSession(connector=connector, trust_env=False, timeout=session_timeout)
            checker = Checker(pm, timeout=cfg.timeout, scraped=cfg.scraped, stats=stats)

            webhook = None
            if cfg.webhook_url and cfg.webhook_message:
                webhook = WebhookSender(cfg.webhook_url, cfg.webhook_message, session, start_time)
                webhook_task = asyncio.create_task(webhook.run())

            async def _worker():
                while True:
                    t = await _next_task()
                    if t is None:
                        return
                    idx, name = t
                    try:
                        result, data, code = await checker.check(session, name)
                        if result is True:
                            await stats.inc_works()
                        elif result is False:
                            await stats.inc_taken()
                        else:
                            await stats.inc_errors()
                        if webhook and result is True:
                            webhook.enqueue(name)
                    except Exception:
                        await stats.inc_errors()

            tasks = [asyncio.create_task(_worker()) for _ in range(min(cfg.concurrency, 200))]

            # Update UI periodically
            while not self._stop_event.is_set():
                await asyncio.sleep(0.5)
                snap = await stats.snapshot()
                elapsed = time.time() - start_time
                pct = (snap["works"] + snap["taken"]) / max(total, 1) * 100

                self.after(0, lambda s=snap, e=elapsed, p=pct: self._update_check_stats(s, e, p, total))

                if all(t.done() for t in tasks) and _idx[0] >= total:
                    break

            for t in tasks:
                t.cancel()
            if webhook:
                webhook_task.cancel()
            await session.close()

            elapsed = time.time() - start_time
            snap = stats._lock and await stats.snapshot() or {}
            self.after(0, lambda: self._show_results(snap if snap else {
                "requests": stats.requests, "works": stats.works, "taken": stats.taken,
                "ratelimited": stats.ratelimited, "errors": stats.errors,
            }, elapsed))

        loop.run_until_complete(_run())
        loop.close()

    def _update_check_stats(self, snap: dict, elapsed: float, pct: float, total: int) -> None:
        self._check_progress.configure(value=min(pct, 100))
        self._stat_labels["available"].configure(text=str(snap["works"]))
        self._stat_labels["taken"].configure(text=str(snap["taken"]))
        self._stat_labels["reqs"].configure(text=str(snap["requests"]))
        self._stat_labels["rps"].configure(text=f"{snap['requests'] / max(elapsed, 0.1):.0f}")
        self._stat_labels["errors"].configure(text=str(snap["errors"]))
        self._stat_labels["elapsed"].configure(text=f"{elapsed:.0f}s")

    def _stop_checking(self) -> None:
        self._stop_event.set()

    def _show_results(self, snap: dict, elapsed: float) -> None:
        self._clear_body()
        self._status_label.configure(text="  Done  ", fg=SUCCESS)

        frame = tk.Frame(self._body, bg=BG)
        frame.pack(expand=True, fill="both", padx=30, pady=30)

        tk.Label(
            frame, text="Checking Complete", font=("Segoe UI", 16, "bold"),
            fg=SUCCESS, bg=BG,
        ).pack(pady=(0, 16))

        # Results
        results_frame = tk.Frame(frame, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        results_frame.pack(fill="x", pady=(0, 16))

        for label, value, color in [
            ("Available", str(snap.get("works", 0)), SUCCESS),
            ("Taken", str(snap.get("taken", 0)), DANGER),
            ("Requests", str(snap.get("requests", 0)), TXT),
            ("Rate Limited", str(snap.get("ratelimited", 0)), WARNING),
            ("Errors", str(snap.get("errors", 0)), DANGER),
            ("Elapsed", f"{elapsed:.0f}s", MUTED),
        ]:
            row = tk.Frame(results_frame, bg=BG2)
            row.pack(fill="x", padx=16, pady=6)
            tk.Label(row, text=label, font=("Segoe UI", 10), fg=MUTED, bg=BG2, width=14, anchor="w").pack(side="left")
            tk.Label(row, text=value, font=("Segoe UI", 10, "bold"), fg=color, bg=BG2, anchor="w").pack(side="left")

        tk.Label(
            frame, text=f"Results saved to {RESULTS_DIR / 'hits.txt'}",
            font=("Segoe UI", 9), fg=MUTED, bg=BG,
        ).pack(pady=(8, 16))

        # Buttons
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill="x")
        self._make_button(
            btn_frame, "New Check", PRIMARY, self._show_wizard_screen,
        ).pack(side="left", padx=(0, 10))
        self._make_button(
            btn_frame, "Exit", BG3, self.destroy,
            fg=TXT, bg=BG3, hover_bg=BORDER,
        ).pack(side="left")

    # ── Helpers ──

    def _make_button(
        self, parent, text, bg, command,
        fg="#fff", hover_bg=None, width=None, **kwargs,
    ) -> tk.Button:
        btn = tk.Button(
            parent, text=text, command=command,
            font=("Segoe UI", 10, "bold"),
            fg=fg, bg=bg, activebackground=hover_bg or bg,
            activeforeground=fg, relief="flat", cursor="hand2",
            padx=16, pady=8, **kwargs,
        )
        if width:
            btn.configure(width=width)

        def _enter(e):
            if hover_bg:
                btn.configure(bg=hover_bg)
        def _leave(e):
            btn.configure(bg=bg)

        btn.bind("<Enter>", _enter)
        btn.bind("<Leave>", _leave)
        return btn


def main() -> None:
    ensure_dir(DATA_DIR, LOGS_DIR, RESULTS_DIR)
    ensure_file(DATA_DIR / "config.json")
    ensure_file(DATA_DIR / "proxies.txt")
    ensure_file(DATA_DIR / "names_to_check.txt")
    ensure_file(LOGS_DIR / "error.txt", clean=True)

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
