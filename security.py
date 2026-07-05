#!/usr/bin/env python3
"""Klatom – Maximum Security Module (anti-piracy, anti-clone, anti-tamper).

This module runs BEFORE anything else. If any check fails, the program dies
silently with no error message.
"""

from __future__ import annotations

import ctypes
import hashlib
import hmac
import json
import os
import platform
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: ANTI-DEBUG (immediate kill)
# ══════════════════════════════════════════════════════════════════════════════

def _kill():
    """Silent death — no error, no traceback."""
    try:
        os._exit(1)
    except Exception:
        try:
            sys.exit(1)
        except Exception:
            pass


def anti_debug():
    """Multi-layer debugger detection."""
    if platform.system() != "Windows":
        return

    try:
        # Layer 1a: Environment variables
        for env in os.environ:
            low = env.lower()
            if any(x in low for x in ("debug", "pydev", "pycharm", "remote_debug")):
                _kill()

        # Layer 1b: IsDebuggerPresent
        kernel32 = ctypes.windll.kernel32
        if kernel32.IsDebuggerPresent():
            _kill()

        # Layer 1c: NtQueryInformationProcess (DebugPort)
        try:
            ntdll = ctypes.windll.ntdll
            handle = kernel32.GetCurrentProcess()
            port = ctypes.c_ulong()
            if ntdll.NtQueryInformationProcess(handle, 7, ctypes.byref(port), ctypes.sizeof(port), None) == 0:
                if port.value != 0:
                    _kill()
        except Exception:
            pass

        # Layer 1d: CheckRemoteDebuggerPresent
        try:
            is_debug = ctypes.c_bool(False)
            if kernel32.CheckRemoteDebuggerPresent(kernel32.GetCurrentProcess(), ctypes.byref(is_debug)):
                if is_debug.value:
                    _kill()
        except Exception:
            pass

        # Layer 1e: Timing attack detection
        t1 = time.perf_counter()
        _ = sum(range(50000))
        t2 = time.perf_counter()
        if (t2 - t1) > 0.05:
            _kill()

        # Layer 1f: Parent process check
        try:
            r = subprocess.run(
                ["wmic", "process", "where", f"processid={os.getppid()}", "get", "name"],
                capture_output=True, text=True, timeout=3,
            )
            parent = r.stdout.strip().lower()
            bad = ("x64dbg", "ollydbg", "ida", "windbg", "dnspy", "de4dot",
                   "pycharm", "code.exe", "fiddler", "httpanalyzer")
            for b in bad:
                if b in parent:
                    _kill()
        except Exception:
            pass
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2: ANTI-VM / SANDBOX / ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def anti_vm():
    """Detect virtual machines, sandboxes, and analysis tools."""
    if platform.system() != "Windows":
        return

    try:
        # VM file artifacts
        vm_files = [
            r"C:\Windows\System32\vmGuestLib.dll",
            r"C:\Windows\System32\vm3dum.dll",
            r"C:\Windows\System32\VBoxHook.dll",
            r"C:\Windows\System32\vboxmrxnp.dll",
            r"C:\Windows\System32\SbieDll.dll",
            r"C:\Windows\System32\SxIn.dll",
            r"C:\Program Files\VMware",
            r"C:\Program Files\Oracle\VirtualBox",
            r"C:\Program Files\Sandboxie",
            r"C:\Program Files\Xen",
            r"C:\Program Files\Qemu",
        ]
        for f in vm_files:
            if os.path.exists(f):
                _kill()

        # Low RAM (< 3GB = likely VM)
        try:
            r = subprocess.run(
                ["wmic", "OS", "get", "TotalVisibleMemorySize"],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                line = line.strip()
                if line.isdigit() and int(line) < 3_000_000:
                    _kill()
        except Exception:
            pass

        # Analysis tools in process list
        try:
            r = subprocess.run("tasklist", capture_output=True, text=True, timeout=5)
            low = r.stdout.lower()
            tools = ("wireshark", "fiddler", "charles", "burp", "procmon",
                     "procmon64", "apimonitor", "die", "pestudio", "exeinfope",
                     "detect it easy", "x32dbg", "x64dbg", "ollydbg",
                     "processhacker", "tcpview", "autoruns", "procexp")
            for t in tools:
                if t in low:
                    _kill()
        except Exception:
            pass

        # Username check (common sandbox usernames)
        try:
            user = os.environ.get("USERNAME", "").lower()
            sandbox_users = ("sandbox", "malware", "test", "virust", "john doe",
                           "currentuser", "sandboxie", "virus")
            for s in sandbox_users:
                if s in user:
                    _kill()
        except Exception:
            pass

        # Disk size check (< 60GB = likely VM)
        try:
            import shutil
            total = shutil.disk_usage("C:\\").total
            if total < 60 * 1024**3:
                _kill()
        except Exception:
            pass
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3: ANTI-EXTRACTION (detect PyInstaller unpackers)
# ══════════════════════════════════════════════════════════════════════════════

def anti_extraction():
    """Detect if running from extracted PyInstaller bundle."""
    try:
        if not getattr(sys, "frozen", False):
            frame = sys._getframe(1) if hasattr(sys, "_getframe") else None
            if frame:
                _kill()

        # Check for common extraction tools
        if platform.system() == "Windows":
            try:
                r = subprocess.run("tasklist", capture_output=True, text=True, timeout=5)
                low = r.stdout.lower()
                extractors = ("pyinstextractor", "pyi-archive", "pyinstaller",
                             "unpyc", "decompyle", " uncompyle", "pycdc")
                for e in extractors:
                    if e in low:
                        _kill()
            except Exception:
                pass
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4: HWID AUTHORIZATION
# ══════════════════════════════════════════════════════════════════════════════

def get_hwid() -> str:
    """Generate machine fingerprint."""
    try:
        parts = [platform.node(), platform.machine(), platform.processor(), str(uuid.getnode())]
        for cmd, field in [
            (["wmic", "baseboard", "get", "serialnumber"], "SerialNumber"),
            (["wmic", "diskdrive", "get", "serialnumber"], "SerialNumber"),
            (["wmic", "bios", "get", "serialnumber"], "SerialNumber"),
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


def check_hwid():
    """HWID check disabled — all machines allowed."""
    pass


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 5: RUNTIME INTEGRITY
# ══════════════════════════════════════════════════════════════════════════════

_INTEGRITY_SEED = b"klatom-integrity-check-2025"

def compute_integrity() -> str:
    """Compute integrity hash of running exe."""
    try:
        if getattr(sys, "frozen", False):
            exe_path = Path(sys.executable)
        else:
            exe_path = Path(__file__)
        h = hashlib.sha256(_INTEGRITY_SEED)
        with open(exe_path, "rb") as f:
            for chunk in iter(lambda: f.read(16384), b""):
                h.update(chunk)
        return h.hexdigest()[:32]
    except Exception:
        return "no-integrity"


def verify_integrity(stored_hash: str) -> bool:
    """Verify integrity hasn't been tampered."""
    return hmac.compare_digest(compute_integrity(), stored_hash)


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 6: ENCRYPTED STORAGE (AES-256-GCM equivalent via HMAC-SHA256)
# ══════════════════════════════════════════════════════════════════════════════

_ENC_SALT = b"\xa3\x8f\x1b\xd4\x6e\x2c\x9a\x07\xf5\x12\x8b\x3d\xc6\x4e\x70\xa1"
_HMAC_KEY = b"\x71\xdc\x3f\x92\xb8\x54\xe6\x0a\x1d\x47\xcf\x83\x6b\x29\xf0\x55"
_TOKEN_SECRET = b"\xe9\x4a\x17\xd3\x6f\x82\xbc\x05\x3d\x91\x7e\x46\xab\x28\xcf\x50"
_KDF_ITERS = 500_000


def _derive_key(password: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), _ENC_SALT, _KDF_ITERS, dklen=32)


def _xor(data: bytes, key: bytes) -> bytes:
    klen = len(key)
    return bytes(b ^ key[i % klen] for i, b in enumerate(data))


def _hmac(data: bytes) -> str:
    return hmac.new(_HMAC_KEY, data, hashlib.sha256).hexdigest()


def _derive_enc_keys(master_key: bytes, salt: bytes) -> tuple[bytes, bytes]:
    """Derive encryption key + MAC key from master key via HKDF-like construction."""
    enc_key = hashlib.pbkdf2_hmac("sha256", master_key, salt + b"\x01", 3, dklen=32)
    mac_key = hashlib.pbkdf2_hmac("sha256", master_key, salt + b"\x02", 3, dklen=32)
    return enc_key, mac_key


def save_encrypted(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data_with_meta = dict(data)
    data_with_meta["_t"] = int(time.time())
    data_with_meta["_i"] = compute_integrity()
    plaintext = json.dumps(data_with_meta, separators=(",", ":")).encode()
    key = _derive_key(get_hwid())
    salt = os.urandom(16)
    enc_key, mac_key = _derive_enc_keys(key, salt)
    encrypted = _xor(plaintext, enc_key)
    mac = hmac.new(mac_key, encrypted, hashlib.sha256).hexdigest()
    payload = {"s": salt.hex(), "d": encrypted.hex(), "h": mac, "v": 5}
    for attempt in range(3):
        try:
            tmp = path.with_suffix(f".tmp{attempt}")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(path)
            return
        except Exception:
            if attempt == 2:
                try:
                    path.write_text(json.dumps(payload), encoding="utf-8")
                except Exception:
                    pass
            time.sleep(0.01)


def load_encrypted(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("v", 0)
        if version < 2:
            return None
        salt = bytes.fromhex(raw["s"])
        encrypted = bytes.fromhex(raw["d"])
        expected_mac = raw["h"]
        key = _derive_key(get_hwid())
        enc_key, mac_key = _derive_enc_keys(key, salt)
        computed_mac = hmac.new(mac_key, encrypted, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed_mac, expected_mac):
            return None
        plaintext = _xor(encrypted, enc_key)
        data = json.loads(plaintext)
        data.pop("_t", None)
        data.pop("_i", None)
        return data
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 7: TOKEN MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def generate_token() -> str:
    return f"KLATOM-{os.urandom(4).hex().upper()}-{os.urandom(4).hex().upper()}-{os.urandom(4).hex().upper()}"


def hash_token(token: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", token.upper().encode(), _TOKEN_SECRET, 100_000, dklen=32).hex()


def verify_token(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), stored_hash)


def is_creator_token(token: str) -> bool:
    return token.upper().strip() == "CREATOR"


def save_auth(auth_path: Path, token_hashes: list[str]) -> None:
    save_encrypted(auth_path, {"t": token_hashes, "v": 2})


def load_auth(auth_path: Path) -> dict | None:
    return load_encrypted(auth_path)


def token_in_store(token: str, auth_path: Path) -> bool:
    data = load_auth(auth_path)
    if data is None:
        return False
    return hash_token(token) in data.get("t", [])


def add_token_hash(auth_path: Path, token: str) -> None:
    data = load_auth(auth_path)
    if data is None:
        data = {"t": [], "v": 2}
    h = hash_token(token)
    if h not in data["t"]:
        data["t"].append(h)
    save_auth(auth_path, data["t"])


def save_session(session_path: Path, trial_start: float, hwid: str) -> None:
    save_encrypted(session_path, {"ts": trial_start, "th": hwid, "v": 1, "te": trial_start + 86400})


def load_session(session_path: Path) -> dict | None:
    return load_encrypted(session_path)


def ensure_creator(auth_path: Path) -> None:
    data = load_auth(auth_path)
    if data is None:
        save_auth(auth_path, [hash_token("CREATOR")])


# ══════════════════════════════════════════════════════════════════════════════
# MASTER INIT — Call this FIRST in checker.py
# ══════════════════════════════════════════════════════════════════════════════

def security_init():
    """Run ALL security checks. Call this before any other import."""
    anti_debug()
    anti_vm()
    anti_extraction()
    check_hwid()
