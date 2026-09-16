"""One private room, one durable exchange. Local save APIs remain unchanged by default."""
from __future__ import annotations

import json
import hashlib
import secrets
import threading
import time
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlsplit

from .remote_crypto import Channel, PEER_ROLES, encode, decode, new_identity, public_key
from .storage import read_json, write_json, atomic_write
from .save import Pokemon, Save, evolution_target


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Relay redirects are not accepted", headers, fp)


urlopen = build_opener(NoRedirect()).open


def configure(path, relay, credential, role, room=None):
    if path.exists():
        raise ValueError("Remote config already exists. Keep it for recovery.")
    parsed = urlsplit(relay)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        raise ValueError("Relay must be an HTTPS URL without credentials, query or fragment")
    if len(credential) < 32 or role not in PEER_ROLES:
        raise ValueError("Invalid credential or role")
    room = room or secrets.token_hex(16)
    from .relay import ROOM
    if not ROOM.fullmatch(room):
        raise ValueError("Room code must be 32 lowercase hexadecimal characters")
    write_json(path, dict(relay=relay.rstrip("/"), credential=credential, role=role,
                         room=room, private=new_identity(), lease=secrets.token_hex(16)))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return room


class Peer:
    def __init__(self, config, root):
        self.config = read_json(config)
        if urlsplit(self.config["relay"]).scheme != "https":
            raise ValueError("Remote mode requires an HTTPS relay")
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "peer.json"
        identity = [self.config["room"], self.config["role"], public_key(self.config["private"])]
        self.state = (read_json(self.path) if self.path.exists() else
                      dict(identity=identity, public=None, sequence=0, seen=0,
                           local={"verified": False}, remote={}))
        if self.state["identity"] != identity:
            raise ValueError("This recovery directory belongs to a different room or bridge")
        self.lock = threading.RLock()
        self.channel = None
        if self.state["public"]:
            self.channel = Channel(self.config["private"], self.state["public"],
                                   self.config["room"], self.config["role"])
        self.error = "Connecting to relay"
        self.last_contact = 0.0
        self.persist()

    def persist(self):
        write_json(self.path, self.state)

    def update(self, **changes):
        with self.lock:
            if any(self.state["local"].get(k) != v for k, v in changes.items()):
                self.state["local"].update(changes)
                self.persist()

    def values(self):
        with self.lock:
            return dict(self.state["local"]), dict(self.state["remote"])

    def verified(self):
        # A private room has one relay-enforced slot per role. Once the peer's
        # identity is pinned and the encrypted channel exists, no separate
        # comparison ceremony is needed for this trusted self-hosted mode.
        return self.channel is not None

    def verify(self, phrase):
        with self.lock:
            if not self.channel or phrase != self.channel.phrase:
                raise ValueError("Verification code changed. Compare it with your friend.")
            self.update(verified=True)

    def exchange(self):
        with self.lock:
            self.state["sequence"] += 1
            self.persist()  # Sequence survives crashes before transmission.
            envelope = (self.channel.seal(self.state["sequence"], self.state["local"])
                        if self.channel else None)
            body = dict(room=self.config["room"], role=self.config["role"],
                        public=public_key(self.config["private"]),
                        lease=self.config["lease"], envelope=envelope)
        request = Request(self.config["relay"] + "/v1/exchange",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
            "Authorization": "Bearer " + self.config["credential"],
            "User-Agent": "PokeTrader-Bridge/0.3"})
        with urlopen(request, timeout=8) as response:
            data = response.read(16385)
            if len(data) > 16384:
                raise ValueError("Oversized relay response")
            result = json.loads(data)
        with self.lock:
            if result.get("public"):
                if self.state["public"] and self.state["public"] != result["public"]:
                    raise ValueError("Peer identity changed. Keep recovery records; do not approve.")
                if not self.channel:
                    self.channel = Channel(self.config["private"], result["public"],
                                           self.config["room"], self.config["role"])
                    self.state["public"] = result["public"]
                    self.state["local"]["verified"] = True
                envelope = result.get("envelope")
                if envelope:
                    value = self.channel.open(envelope)
                    if envelope["sequence"] > self.state["seen"]:
                        self.state["seen"] = envelope["sequence"]
                        self.state["remote"] = value
                        self.last_contact = time.monotonic()
                self.persist()
            self.error = "" if result else "Waiting for your friend"


class RemoteBackend:
    label = "REMOTE EXPERIMENTAL"

    def __init__(self, config, root):
        self.peer = Peer(config, root)
        if self.peer.config["role"] != "source":
            raise ValueError("The 3DS bridge requires a source config")
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._sync, daemon=True)
        self.thread.start()

    def _sync(self):
        while not self.stop_event.is_set():
            try:
                self.peer.exchange()
            except Exception as exc:
                self.peer.error = f"Relay unavailable or rejected message: {type(exc).__name__}. Recovery retained."
            self.stop_event.wait(1)

    def preflight(self):
        pass

    def stop(self):
        self.stop_event.set()
        self.thread.join(10)

    def attach(self, directory, trainer_id):
        if read_json(directory / "state.json").get("remote_room") != self.peer.config["room"]:
            raise ValueError("Restore the remote config for this pending exchange")
        local, _ = self.peer.values()
        if local.get("trade_id") not in (None, directory.name):
            raise ValueError("This room already belongs to another exchange. Create a new room after recovery.")
        if self.peer.verified():
            offered = (directory / "offered.pk3").read_bytes()
            if evolution_target(Pokemon(offered)):
                raise ValueError("Remote offers must not evolve by trade")
            self.peer.update(trade_id=directory.name, offer=encode(offered),
                companion=encode((directory / "companion.pk3").read_bytes()), trainer_id=trainer_id)

    def poll(self, directory, trainer_id):
        self.attach(directory, trainer_id)
        local, remote = self.peer.values()
        if remote.get("trade_id") != directory.name:
            return {"state": "running", "message": self.peer.error or "Waiting for the Switch bridge."}
        if remote.get("phase") == "cancelled":
            return {"state": "cancelled", "message": "Cancelled before commitment."}
        if remote.get("phase") == "uncertain":
            return {"state": "uncertain", "message": "Inspect the Switch. No automatic repeat is allowed."}
        proposal = remote.get("proposal")
        preview = {}
        if proposal and proposal.get("cancelled"):
            self.peer.update(validated=None, approval=None)
            return {"state": "running", "message": "Switch selection cancelled. Waiting for a new offer."}
        if proposal and proposal.get("revision"):
            incoming = decode(proposal["pokemon"])
            try:
                Save((directory / "original.sav").read_bytes()).replace(
                    read_json(directory / "state.json")["index"],
                    (directory / "offered.pk3").read_bytes(), incoming)
            except ValueError as exc:
                self.peer.update(validated=None, approval=None, rejection=str(exc))
                return {"state": "running", "message": f"Offer rejected: {exc}"}
            revision = proposal["revision"]
            if local.get("validated") != revision:
                self.peer.update(validated=revision, approval=revision, rejection=None)
            from .service import trade_art
            mon = Pokemon(incoming)
            preview = dict(received=mon.summary, received_art=trade_art(mon))
            if remote.get("phase") == "offer":
                return dict(state="running", message="Switch offer validated and accepted automatically.",
                            **preview)
        if remote.get("phase") in ("committed", "saved"):
            incoming = decode(remote["receipt"])
            if not proposal or incoming != decode(proposal["pokemon"]):
                raise ValueError("Receipt differs from the approved Switch offer. Inspect both consoles.")
            atomic_write(directory / "received.pk3", incoming)
            from .service import trade_art
            mon = Pokemon(incoming)
            return dict(state="received", message="Switch confirmed the trade. Preparing verified save.",
                        received=mon.summary, received_art=trade_art(mon))
        return dict(state="running", message=remote.get("message") or "Waiting for the Switch player.",
                    **preview)

    def approve(self, revision):
        local, remote = self.peer.values()
        if not self.peer.verified() or local.get("validated") != revision or remote.get("proposal", {}).get("revision") != revision:
            raise ValueError("Offer changed or pairing not verified. Refresh before approving.")
        self.peer.update(approval=revision)

    def cancel(self):
        self.peer.update(cancel=True, approval=None)

    def run(self, directory, trainer_id):
        raise RuntimeError("Remote backend is driven by durable polling, never a radio worker")


class SourcePairBackend:
    """Direct save-record exchange used only by source-a/source-b rooms."""

    label = "REMOTE 3DS PAIR EXPERIMENTAL"

    def __init__(self, config, root):
        self.peer = Peer(config, root)
        if self.peer.config["role"] not in ("source-a", "source-b"):
            raise ValueError("A 3DS pair requires source-a and source-b configs")
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._sync, daemon=True)
        self.thread.start()

    def _sync(self):
        while not self.stop_event.is_set():
            try:
                self.peer.exchange()
            except Exception as exc:
                self.peer.error = f"Relay unavailable or rejected message: {type(exc).__name__}. Recovery retained."
            self.stop_event.wait(1)

    def preflight(self):
        pass

    def stop(self):
        self.stop_event.set()
        self.thread.join(10)

    def reserve(self, trade_id):
        local, remote = self.peer.values()
        reserved = local.get("reserved_id")
        if reserved in (None, trade_id):
            return
        if not (local.get("applied") and remote.get("applied")):
            raise ValueError("This room still has an unfinished exchange.")
        self.peer.update(reserved_id=None, local_offer=None, proposal=None, validated=None,
                         phase="waiting", cancel=False, applied=False)

    def _proposal_id(self, local_offer, remote_offer):
        ordered = (local_offer + remote_offer if self.peer.config["role"] == "source-a"
                   else remote_offer + local_offer)
        return hashlib.sha256(ordered.encode()).hexdigest()

    def attach(self, directory):
        if read_json(directory / "state.json").get("remote_room") != self.peer.config["room"]:
            raise ValueError("Restore the remote config for this pending exchange")
        local, _ = self.peer.values()
        if local.get("reserved_id") != directory.name:
            raise ValueError("This room belongs to another local exchange")
        offer = (directory / "offered.pk3").read_bytes()
        Pokemon(offer).check_tradeable()
        if evolution_target(Pokemon(offer)):
            raise ValueError("Remote offers must not evolve by trade")
        encoded = encode(offer)
        if local.get("local_offer") not in (None, encoded):
            raise ValueError("Local offer changed after joining the room")
        self.peer.update(local_offer=encoded, phase="offering")

    def poll(self, directory, _trainer_id):
        self.attach(directory)
        local, remote = self.peer.values()
        if local.get("cancel") or remote.get("cancel"):
            if local.get("phase") == "released" or remote.get("phase") == "released":
                return {"state": "uncertain",
                        "message": "A save may already have been released. Inspect both 3DS systems."}
            return {"state": "cancelled", "message": "Cancelled before either save was released."}
        remote_offer = remote.get("local_offer")
        if not remote_offer:
            return {"state": "running", "message": self.peer.error or "Waiting for the other 3DS bridge."}

        incoming = decode(remote_offer)
        try:
            Save((directory / "original.sav").read_bytes()).replace(
                read_json(directory / "state.json")["index"],
                (directory / "offered.pk3").read_bytes(), incoming)
        except ValueError as exc:
            self.peer.update(validated=None, rejection=str(exc))
            return {"state": "running", "message": f"Peer offer rejected: {exc}"}

        proposal = self._proposal_id(local["local_offer"], remote_offer)
        if local.get("validated") != proposal:
            self.peer.update(proposal=proposal, validated=proposal, rejection=None,
                             message="Offer validated. Waiting for the other 3DS bridge.")
            local, remote = self.peer.values()
        mon = Pokemon(incoming)
        from .service import trade_art
        preview = dict(received=mon.summary, received_art=trade_art(mon))
        if remote.get("validated") != proposal or remote.get("proposal") != proposal:
            return dict(state="running", message="Offer validated. Waiting for the other 3DS bridge.",
                        **preview)

        atomic_write(directory / "received.pk3", incoming)
        self.peer.update(phase="released", message="Both offers validated; replacement save released.")
        return dict(state="received", message="Both 3DS offers matched. Preparing the replacement save.",
                    **preview)

    def approve(self, _revision):
        raise ValueError("3DS pair rooms approve validated selections automatically")

    def cancel(self):
        self.peer.update(cancel=True)

    def run(self, directory, trainer_id):
        raise RuntimeError("3DS pair exchanges are driven by durable polling")


class SwitchWorker:
    def __init__(self, config, root, backend):
        self.config_path = config
        self.control_lock = threading.RLock()
        self.peer = Peer(config, root / "rooms" / read_json(config)["room"])
        if self.peer.config["role"] != "switch":
            raise ValueError("The Switch bridge requires a switch config")
        self.backend = backend
        self.backend.remote_gate = True
        self.root = root
        self.directory = self.peer.root / "exchange"
        self.directory.mkdir(exist_ok=True)
        self.stop_event = threading.Event()
        self.radio = None
        local, _ = self.peer.values()
        if local.get("launched") and local.get("phase") not in ("saved", "receipt", "cancelled"):
            self._finish("Bridge restarted. Inspect the Switch before confirming recovery.")

    def can_join(self):
        local, remote = self.peer.values()
        terminal = local.get("phase") == "cancelled" or (local.get("phase") == "saved" and remote.get("applied"))
        return (not local.get("verified") or terminal) and not (self.radio and self.radio.is_alive())

    def join(self, room):
        from .relay import ROOM
        if not isinstance(room, str) or not ROOM.fullmatch(room):
            raise ValueError("Enter the 32-character room code from your friend")
        with self.control_lock:
            if room == self.peer.config["room"]:
                return
            if not self.can_join():
                raise ValueError("Finish or recover the paired exchange before joining another room")
            next_root = self.root / "rooms" / room
            connection = next_root / "connection.json"
            if not connection.exists():
                configure(connection, self.peer.config["relay"], self.peer.config["credential"], "switch", room)
            next_peer = Peer(connection, next_root)
            # Keep the old identity with its recovery records before switching the launch config.
            write_json(self.peer.root / "connection.json", self.peer.config)
            write_json(self.config_path, next_peer.config)
            self.peer = next_peer
            self.directory = next_root / "exchange"
            self.directory.mkdir(exist_ok=True)
            self.radio = None
            local, _ = self.peer.values()
            if local.get("launched") and local.get("phase") not in ("saved", "receipt", "cancelled"):
                self._finish("Returned to an interrupted room. Inspect the Switch.")

    def _publish_receipt(self, phase, message):
        local, _ = self.peer.values()
        receipt = (self.directory / "received.pk3").read_bytes()
        Pokemon(receipt)
        proposal = local.get("proposal")
        if not proposal or receipt != decode(proposal["pokemon"]):
            raise ValueError("Receipt differs from approved offer")
        self.peer.update(phase=phase, receipt=encode(receipt), message=message)

    def _finish(self, message):
        try:
            self._publish_receipt("saved", "Switch trade confirmed and link cleanup completed.")
        except (OSError, ValueError):
            self.peer.update(phase="uncertain", message=message)

    def _run(self, trainer_id):
        try:
            self.backend.run(self.directory, trainer_id)
        except Exception:
            pass
        local, _ = self.peer.values()
        cancelled = self.directory / "gate-cancelled.json"
        if cancelled.exists() and not local.get("commit_possible"):
            self.peer.update(phase="cancelled", approval=None, message="Cancelled before commitment.")
        else:
            self._finish("Trade ended without a verified receipt. Inspect the Switch.")

    def _reset_completed_exchange(self):
        for name in ("gate-offer.json", "gate-decision.json", "gate-cancelled.json",
                     "offered.pk3", "companion.pk3", "received.pk3"):
            (self.directory / name).unlink(missing_ok=True)
        self.peer.update(trade_id=None, launched=False, phase="waiting", source_offer=None,
                         proposal=None, approval=None, cancel=False, commit_possible=False,
                         receipt=None, message="Waiting for the next trusted-room exchange.")
        self.radio = None

    def advance(self):
        local, remote = self.peer.values()
        if not self.peer.verified():
            return
        if (local.get("phase") == "saved" and remote.get("trade_id")
                and remote.get("trade_id") != local.get("trade_id")):
            self._reset_completed_exchange()
            local, remote = self.peer.values()
        if not local.get("launched") and remote.get("trade_id"):
            if local.get("trade_id") not in (None, remote["trade_id"]):
                raise ValueError("Room belongs to another exchange")
            if remote.get("cancel") or local.get("cancel"):
                self.peer.update(trade_id=remote["trade_id"], phase="cancelled")
                return
            offered, companion = decode(remote["offer"]), decode(remote["companion"])
            Pokemon(offered).check_tradeable()
            Pokemon(companion).check_tradeable()
            if evolution_target(Pokemon(offered)):
                raise ValueError("Trade evolution is unsupported")
            atomic_write(self.directory / "offered.pk3", offered)
            atomic_write(self.directory / "companion.pk3", companion)
            self.backend.preflight()
            # Durable BEFORE process launch. A crash in this gap requires reconciliation.
            self.peer.update(trade_id=remote["trade_id"], launched=True, phase="running",
                             source_offer=remote["offer"],
                             message="Lead a Direct Corner trade, accept 3DSLINK, sit on the left.")
            self.radio = threading.Thread(target=self._run, args=(remote["trainer_id"],), daemon=True)
            self.radio.start()
            return
        if not self.radio or not self.radio.is_alive():
            return
        if remote.get("offer") != local.get("source_offer"):
            raise ValueError("Source offer changed after launching the radio session")
        receipt_path = self.directory / "received.pk3"
        if local.get("commit_possible") and local.get("phase") == "committing" and receipt_path.exists():
            self._publish_receipt("committed", "Switch confirmed the trade; finishing link cleanup.")
            local, remote = self.peer.values()
        if remote.get("applied"):
            return
        proposal_path = self.directory / "gate-offer.json"
        if not proposal_path.exists():
            return
        proposal = read_json(proposal_path)
        if local.get("proposal") != proposal and not local.get("commit_possible"):
            self.peer.update(proposal=proposal, approval=proposal.get("revision"), phase="offer")
            local, remote = self.peer.values()
        revision = proposal["revision"]
        if proposal.get("cancelled"):
            return
        cancel = local.get("cancel") or remote.get("cancel") or remote.get("rejection")
        if cancel and not local.get("commit_possible"):
            write_json(self.directory / "gate-decision.json", dict(revision=revision, action="decline"))
        elif (local.get("approval") == revision and remote.get("approval") == revision
              and remote.get("validated") == revision and not local.get("commit_possible")
              and time.monotonic() - self.peer.last_contact < 10):
            self.peer.update(commit_possible=True, phase="committing",
                             message="Both offers approved. Waiting for Switch completion.")
            write_json(self.directory / "gate-decision.json", dict(revision=revision, action="approve"))

    def approve(self, revision):
        local, remote = self.peer.values()
        if local.get("phase") != "offer" or local.get("proposal", {}).get("revision") != revision or remote.get("validated") != revision:
            raise ValueError("Wait for the 3DS bridge to validate the current offer")
        self.peer.update(approval=revision)

    def cancel(self):
        self.peer.update(cancel=True, approval=None)

    def saved(self):
        local, _ = self.peer.values()
        if local.get("phase") != "receipt":
            raise ValueError("A verified receipt and completed process are required")
        self.peer.update(phase="saved", message="Switch player confirmed saving and leaving the room.")

    def run(self):
        while not self.stop_event.is_set():
            try:
                peer = self.peer
                peer.exchange()
                with self.control_lock:
                    if self.peer is peer:
                        self.advance()
            except Exception as exc:
                self.peer.error = f"Waiting for recovery: {type(exc).__name__}"
            self.stop_event.wait(1)

    def close(self):
        self.stop_event.set()
        self.backend.stop()
        if self.radio:
            self.radio.join(20)


class SwitchPairWorker:
    """Two-session coordinator used only by switch-a/switch-b rooms.

    Session one captures and declines each physical Switch's selection. Session
    two starts with the peer's captured selection already in the simulated
    party, then commits only if both Switches select the same records again.
    """

    def __init__(self, config, root, backend, bootstrap_save):
        self.peer = Peer(config, root / "rooms" / read_json(config)["room"])
        if self.peer.config["role"] not in ("switch-a", "switch-b"):
            raise ValueError("A Switch pair requires switch-a and switch-b configs")
        self.backend = backend
        self.backend.remote_gate = True
        self.directory = self.peer.root / "switch-pair"
        self.negotiation = self.directory / "negotiation"
        self.execution = self.directory / "execution"
        self.negotiation.mkdir(parents=True, exist_ok=True)
        self.execution.mkdir(parents=True, exist_ok=True)
        self.stop_event = threading.Event()
        self.radio = None

        save = Save(Path(bootstrap_save).read_bytes())
        candidates = []
        for index in range(420):
            try:
                mon = save.pokemon(index)
                mon.check_tradeable()
                if not evolution_target(mon):
                    candidates.append(mon.pk3)
            except ValueError:
                pass
        if not candidates:
            raise ValueError("Bootstrap save needs a tradeable, non-evolving boxed Pokemon")
        self.bootstrap = (candidates * 2)[:2]
        self.trainer_id = save.trainer_id

        local, _ = self.peer.values()
        if (local.get("negotiation_launched") and not local.get("negotiation_finished")) or (
                local.get("execution_launched") and local.get("phase") not in ("committed", "complete")):
            self.peer.update(phase="uncertain",
                message="Bridge restarted during a radio session. Inspect the Switches; do not retry automatically.")

    @staticmethod
    def _clear_session(directory):
        for name in ("gate-offer.json", "gate-decision.json", "gate-cancelled.json", "received.pk3"):
            (directory / name).unlink(missing_ok=True)

    def _stage(self, directory, offered, companion):
        self._clear_session(directory)
        atomic_write(directory / "offered.pk3", offered)
        atomic_write(directory / "companion.pk3", companion)

    def _run_negotiation(self):
        try:
            self.backend.run(self.negotiation, self.trainer_id)
        except Exception:
            pass
        local, _ = self.peer.values()
        decision = self.negotiation / "gate-decision.json"
        declined = (decision.exists() and read_json(decision).get("action") == "decline")
        if local.get("local_offer") and declined and not (self.negotiation / "received.pk3").exists():
            self.peer.update(negotiation_finished=True, phase="negotiated",
                             message="Offer captured. Leave the room and prepare to trade once more.")
        else:
            self.peer.update(phase="uncertain",
                             message="Negotiation session ended unexpectedly. Inspect the Switch.")

    def _run_execution(self):
        try:
            self.backend.run(self.execution, self.trainer_id)
        except Exception:
            pass
        local, _ = self.peer.values()
        receipt_path = self.execution / "received.pk3"
        if receipt_path.exists() and local.get("commit_possible"):
            receipt = receipt_path.read_bytes()
            if encode(receipt) == local.get("local_offer"):
                self.peer.update(phase="committed", receipt=encode(receipt),
                                 message="Local Switch trade committed. Waiting for the peer receipt.")
                return
        self.peer.update(phase="uncertain",
                         message="Execution ended without the expected receipt. Inspect both Switches.")

    def _launch_negotiation(self):
        self._stage(self.negotiation, self.bootstrap[1], self.bootstrap[0])
        self.peer.update(negotiation_launched=True, phase="negotiating",
                         message="First visit: enter Direct Corner and select the Pokemon you want to trade.")
        self.radio = threading.Thread(target=self._run_negotiation, daemon=True)
        self.radio.start()

    def _proposal_id(self, local_offer, remote_offer):
        if self.peer.config["role"] == "switch-a":
            ordered = local_offer + remote_offer
        else:
            ordered = remote_offer + local_offer
        return hashlib.sha256(ordered.encode()).hexdigest()

    def _launch_execution(self, local, remote):
        offered = decode(remote["local_offer"])
        Pokemon(offered).check_tradeable()
        if evolution_target(Pokemon(offered)):
            raise ValueError("Trade evolution is unsupported")
        self._stage(self.execution, offered, self.bootstrap[0])
        proposal = self._proposal_id(local["local_offer"], remote["local_offer"])
        self.peer.update(execution_launched=True, proposal=proposal, phase="executing",
                         message="Second visit: re-enter Direct Corner and select the same Pokemon again.")
        self.radio = threading.Thread(target=self._run_execution, daemon=True)
        self.radio.start()

    def advance(self):
        local, remote = self.peer.values()
        if not self.peer.verified() or local.get("phase") in ("uncertain", "complete"):
            return
        if not local.get("negotiation_launched"):
            self._launch_negotiation()
            return

        if self.radio and self.radio.is_alive() and local.get("phase") == "negotiating":
            offer_path = self.negotiation / "gate-offer.json"
            if offer_path.exists() and not local.get("local_offer"):
                offer = read_json(offer_path)
                pokemon = decode(offer["pokemon"])
                Pokemon(pokemon).check_tradeable()
                if evolution_target(Pokemon(pokemon)):
                    raise ValueError("Trade evolution is unsupported")
                self.peer.update(local_offer=offer["pokemon"], phase="declining-negotiation",
                                 message="Offer captured. Declining this first session safely.")
                write_json(self.negotiation / "gate-decision.json",
                           dict(revision=offer["revision"], action="decline"))
            return

        local, remote = self.peer.values()
        if (local.get("negotiation_finished") and remote.get("negotiation_finished")
                and local.get("local_offer") and remote.get("local_offer")
                and not local.get("execution_launched")):
            self._launch_execution(local, remote)
            return

        if not (self.radio and self.radio.is_alive() and local.get("phase") == "executing"):
            if (local.get("phase") == "committed"
                    and remote.get("phase") in ("committed", "complete")):
                self.peer.update(phase="complete", message="Both Switch trades committed successfully.")
            return

        offer_path = self.execution / "gate-offer.json"
        if not offer_path.exists():
            return
        offer = read_json(offer_path)
        if offer.get("cancelled"):
            return
        if offer.get("pokemon") != local.get("local_offer"):
            write_json(self.execution / "gate-decision.json",
                       dict(revision=offer["revision"], action="decline"))
            self.peer.update(phase="selection-changed",
                             message="The selected Pokemon changed. Trade declined; start a new room.")
            return
        proposal = local["proposal"]
        if local.get("execution_validated") != proposal:
            self.peer.update(execution_validated=proposal,
                             message="Local offer matches. Waiting for the other Switch.")
            local, remote = self.peer.values()
        if (remote.get("execution_validated") == proposal
                and time.monotonic() - self.peer.last_contact < 10
                and not local.get("commit_possible")):
            self.peer.update(commit_possible=True,
                             message="Both selections match. Completing both trades.")
            write_json(self.execution / "gate-decision.json",
                       dict(revision=offer["revision"], action="approve"))

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.peer.exchange()
                self.advance()
            except Exception as exc:
                self.peer.error = f"Waiting for recovery: {type(exc).__name__}"
            self.stop_event.wait(1)

    def close(self):
        self.stop_event.set()
        self.backend.stop()
        if self.radio:
            self.radio.join(20)
