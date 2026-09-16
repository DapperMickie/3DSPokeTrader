"""Persistent, idempotent exchange state. No automatic retry of a radio trade."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
import threading

from .save import Save, Pokemon, SaveError
from .storage import atomic_write, write_json, read_json

def trade_art(mon):
    """Presentation only; the original PK3 remains the trade payload."""
    pid = int.from_bytes(mon.pk3[:4], "little")
    ot = int.from_bytes(mon.pk3[4:8], "little")
    shiny = ((pid >> 16) ^ (pid & 65535) ^ (ot >> 16) ^ (ot & 65535)) < 8
    return f"{mon.dex}\t{int(shiny)}"


ID = re.compile(r"^[0-9a-f]{32}$")
BLOCKING = {"running", "uncertain", "received", "import_blocked"}


class Conflict(ValueError):
    pass


def identifier(value):
    if not ID.fullmatch(value):
        raise ValueError("Invalid identifier.")
    return value


class Service:
    def __init__(self, root: Path, backend):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "saves").mkdir(exist_ok=True)
        (self.root / "trades").mkdir(exist_ok=True)
        self.backend = backend
        self.lock = threading.RLock()
        self.threads = []
        self.closing = False
        for path in (self.root / "trades").glob("*/state.json"):
            state = read_json(path)
            if state["state"] == "running":
                # Never relaunch a trade after restart. A receipt can still be confirmed.
                self._finish(path.parent, state, "Bridge restarted during trading.")

    def directory(self, trade_id):
        return self.root / "trades" / identifier(trade_id)

    def state(self, trade_id):
        with self.lock:
            return read_json(self.directory(trade_id) / "state.json")

    def save(self, save_id):
        return Save((self.root / "saves" / (identifier(save_id)+".sav")).read_bytes())

    def upload(self, data):
        parsed = Save(data)
        save_id = sha256(data).hexdigest()[:32]
        with self.lock:
            path = self.root / "saves" / (save_id+".sav")
            if not path.exists():
                atomic_write(path, data)
            elif path.read_bytes() != data:
                raise Conflict("Save identifier collision.")
        return save_id, parsed

    def prepare(self, trade_id, save_id, index):
        directory = self.directory(trade_id)
        with self.lock:
            path = directory / "state.json"
            if path.exists():
                old = read_json(path)
                if old["save_id"] != save_id or old["index"] != index:
                    raise Conflict("Transaction identifier was already used for another selection.")
                return old
            save = self.save(save_id)
            offered = save.pokemon(index)
            offered.check_tradeable()
            companion = save.companion()
            directory.mkdir(exist_ok=True)
            atomic_write(directory / "original.sav", save.data)
            atomic_write(directory / "offered.pk3", offered.pk3)
            atomic_write(directory / "companion.pk3", companion.pk3)
            state = dict(id=trade_id, save_id=save_id, index=index, state="prepared",
                         mode=self.backend.label, message="Ready. Offer a non-evolving Pokemon without mail or an Egg on Switch.",
                         offered=offered.summary, received="", trainer_id=save.trainer_id,
                         offered_art=trade_art(offered))
            write_json(path, state)
            return state

    def start(self, trade_id):
        with self.lock:
            if self.closing:
                raise Conflict("The bridge is shutting down. Keep the pending transaction.")
            state = self.state(trade_id)
            if state["state"] != "prepared":
                return state  # A retried request must never repeat a radio operation.
            for path in (self.root / "trades").glob("*/state.json"):
                other = read_json(path)
                if other["id"] != trade_id and other["state"] in BLOCKING:
                    raise Conflict(f"Resolve transaction {other['id']} before another trade.")
            self.backend.preflight()
            state.update(state="running", message="On Switch: lead a Direct Corner trade, accept 3DSLINK, sit on the left.")
            write_json(self.directory(trade_id) / "state.json", state)
            thread = threading.Thread(target=self._run, args=(trade_id,), daemon=True)
            self.threads.append(thread)
            thread.start()
            return state

    def close(self):
        with self.lock:
            self.closing = True
        stop = getattr(self.backend, "stop", None)
        if stop:
            stop()
        for thread in self.threads:
            thread.join(timeout=20)

    def _run(self, trade_id):
        directory = self.directory(trade_id)
        message = "Trade process ended."
        try:
            code = self.backend.run(directory, self.state(trade_id)["trainer_id"])
            message = f"Trade process exited with code {code}."
        except Exception as exc:
            message = str(exc)
        with self.lock:
            state = self.state(trade_id)
            self._finish(directory, state, message)

    def _finish(self, directory, state, message):
        try:
            data = (directory / "received.pk3").read_bytes()
            mon = Pokemon(data)
            state.update(state="received", received=mon.summary, received_art=trade_art(mon),
                         message="Confirm only after the Switch shows the received Pokemon and has saved. Exit the trading room first.")
        except (FileNotFoundError, SaveError):
            state.update(state="uncertain", message=message+" No valid receipt. Do not repeat the trade; inspect both sides.")
        write_json(directory / "state.json", state)

    def confirm(self, trade_id):
        with self.lock:
            state = self.state(trade_id)
            if state["state"] in ("ready", "applied"):
                return state
            if state["state"] != "received":
                raise Conflict("A valid received Pokemon and completed process are required before confirmation.")
            directory = self.directory(trade_id)
            save = Save((directory / "original.sav").read_bytes())
            try:
                result = save.replace(state["index"], (directory / "offered.pk3").read_bytes(),
                                      (directory / "received.pk3").read_bytes())
            except SaveError as exc:
                state.update(state="import_blocked", message=str(exc))
                write_json(directory / "state.json", state)
                return state
            atomic_write(directory / "result.sav", result)
            state.update(state="ready", result_sha256=sha256(result).hexdigest(),
                         message="Result ready. Download and apply to the unchanged source save.")
            write_json(directory / "state.json", state)
            return state

    def result(self, trade_id):
        with self.lock:
            state = self.state(trade_id)
            if state["state"] not in ("ready", "applied"):
                raise Conflict("The trade has not been confirmed.")
            result = (self.directory(trade_id) / "result.sav").read_bytes()
            if sha256(result).hexdigest() != state["result_sha256"]:
                raise Conflict("Stored result checksum changed.")
            return result

    def applied(self, trade_id):
        with self.lock:
            state = self.state(trade_id)
            if state["state"] not in ("ready", "applied"):
                raise Conflict("There is no confirmed result to acknowledge.")
            state.update(state="applied", message="Save replacement acknowledged by the client.")
            write_json(self.directory(trade_id) / "state.json", state)
            return state

    def resolve_no_trade(self, trade_id):
        """Local CLI only; operator must check that neither side traded."""
        with self.lock:
            state = self.state(trade_id)
            if state["state"] not in ("uncertain", "prepared"):
                raise Conflict("Only a prepared or uncertain transaction can be marked as not traded.")
            state.update(state="cancelled", message="Operator confirmed no trade occurred.")
            write_json(self.directory(trade_id) / "state.json", state)
            return state
