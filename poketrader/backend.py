"""A pinned external trade process. Starting a process never means a trade succeeded."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import signal
import shutil
import threading

UPSTREAM_REVISION = "13809c21b6e992097f98453b7cbc9e2bc30bbf7c"


class LiveBackend:
    label = "LIVE"

    def __init__(self, upstream: Path, keys: Path, phy: str, python: str = sys.executable):
        self.upstream = upstream.resolve()
        self.keys = keys.expanduser().resolve()
        self.phy = phy
        self.python = python
        self.process = None
        self.process_lock = threading.Lock()
        self.stopping = threading.Event()

    def preflight(self):
        if not sys.platform.startswith("linux"):
            raise ValueError("Live trading requires native Linux and a supported Wi-Fi adapter.")
        if not self.keys.is_file():
            raise ValueError("The configured Switch key file is missing.")
        if not (self.upstream / "frlgtrade.py").is_file():
            raise ValueError("The upstream FRLG trading checkout is missing.")
        revision = subprocess.check_output(
            ["git", "-C", str(self.upstream), "rev-parse", "HEAD"], text=True).strip()
        if revision != UPSTREAM_REVISION:
            raise ValueError(f"Use the tested upstream revision {UPSTREAM_REVISION}.")
        dirty = subprocess.check_output(
            ["git", "-C", str(self.upstream), "diff", "HEAD", "--", "*.py"], text=True)
        if dirty:
            raise ValueError("The upstream Python sources have local changes. Use a clean pinned checkout.")
        if not self.phy.startswith("phy") or not self.phy[3:].isdigit():
            raise ValueError("Wi-Fi device must be a name such as phy1.")
        if not Path("/sys/class/ieee80211", self.phy).exists():
            raise ValueError("The configured Wi-Fi adapter is not present. Check iw dev.")
        if shutil.which("nmcli") is None:
            raise ValueError("nmcli is missing. On WSL, install the dedicated-adapter shim from scripts/wsl-nmcli-shim.sh.")
        check = subprocess.run([self.python, "-c", "import ldn, trio, zstandard, Crypto"],
                               capture_output=True, text=True, timeout=20)
        if check.returncode:
            raise ValueError("The configured Python is missing upstream dependencies. Run scripts/setup-bridge.sh.")

    def command(self, directory: Path, trainer_id: int) -> list[str]:
        return [self.python, "-m", "poketrader.upstream_runner", str(self.upstream),
                "--live", "--phy", self.phy, "--keys", str(self.keys),
                "--ot", "3DSLINK", "--version", "leafgreen",
                "--id", f"{trainer_id & 65535}:{trainer_id >> 16}",
                "--trades", "1", "--slot", "1", "--out-size", "80", "--out-format", "pk3",
                "-o", str(directory / "received.pk3"),
                str(directory / "companion.pk3"), str(directory / "offered.pk3")]

    def run(self, directory: Path, trainer_id: int) -> int:
        env = os.environ.copy()
        project = str(Path(__file__).resolve().parent.parent)
        env["PYTHONPATH"] = project + os.pathsep + env.get("PYTHONPATH", "")
        with (directory / "trade.log").open("wb") as log:
            with self.process_lock:
                if self.stopping.is_set():
                    raise RuntimeError("Bridge stopped before launching the trade process.")
                process = subprocess.Popen(self.command(directory, trainer_id), stdout=log,
                                           stderr=subprocess.STDOUT, env=env)
                self.process = process
            try:
                return process.wait(timeout=900)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise RuntimeError("Trade process timed out. Check the Switch before any further trade.")
            finally:
                with self.process_lock:
                    self.process = None

    def stop(self):
        self.stopping.set()
        with self.process_lock:
            process = self.process
        if process is None or process.poll() is not None:
            return
        try:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        except ProcessLookupError:
            pass


class DemoBackend:
    """Explicit rehearsal mode. Never communicates with a console."""
    label = "DEMO - NO SWITCH TRADE"

    def __init__(self, received: bytes):
        from .save import Pokemon
        Pokemon(received).check_tradeable()
        self.received = received

    def preflight(self):
        pass

    def run(self, directory: Path, trainer_id: int) -> int:
        from .storage import atomic_write
        atomic_write(directory / "received.pk3", self.received)
        return 0
