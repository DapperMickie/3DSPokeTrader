"""Exercise encrypted peers through a real TLS relay and persisted crash recovery."""
import datetime
import ipaddress
import json
from pathlib import Path
import ssl
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import urlopen as real_urlopen, Request
from urllib.error import HTTPError

try:
    from cryptography import x509
except ModuleNotFoundError:
    raise unittest.SkipTest("Install .[remote] to run remote integration tests")
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from poketrader.remote_crypto import Channel, new_identity, public_key, encode
from poketrader.relay import Relay
from poketrader.remote import Peer, RemoteBackend, SwitchWorker, configure
from poketrader.__main__ import main
from poketrader.service import Service, Conflict
from poketrader.storage import write_json, read_json, atomic_write
from poketrader.save import Save
from .fixtures import save, pokemon


class CryptoTests(unittest.TestCase):
    def test_context_direction_tampering_and_verification(self):
        a, b = new_identity(), new_identity()
        source = Channel(a, public_key(b), "room", "source")
        switch = Channel(b, public_key(a), "room", "switch")
        self.assertEqual(source.phrase, switch.phrase)
        message = source.seal(1, {"pokemon": "secret"})
        self.assertEqual(switch.open(message), {"pokemon": "secret"})
        self.assertNotIn("secret", json.dumps(message))
        with self.assertRaises(InvalidTag): source.open(message)
        with self.assertRaises(InvalidTag): switch.open(dict(message, sequence=2))
        other_room = Channel(b, public_key(a), "other", "switch")
        with self.assertRaises(InvalidTag): other_room.open(message)

    def test_relay_command_generates_credential_on_first_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"relay-credential"
            class StopServer:
                def __init__(self, _address, credential): self.credential = credential
                def serve_forever(self): raise KeyboardInterrupt
                def server_close(self): pass
            with patch("poketrader.relay.Relay", StopServer):
                self.assertEqual(main(["relay", "--credential-file", str(path)]), 130)
            self.assertEqual(len(path.read_text()), 64)


class ManualRemote(RemoteBackend):
    def _sync(self):
        pass  # Tests drive actual HTTPS exchanges deterministically.


class Radio:
    def __init__(self):
        self.calls = 0
        self.finished = threading.Event()
        self.stop_event = threading.Event()

    def preflight(self): pass
    def stop(self): self.stop_event.set()

    def run(self, directory, trainer_id):
        self.calls += 1
        write_json(directory / "gate-offer.json", dict(revision="offer-1", pokemon=encode(pokemon(133))))
        while not self.stop_event.wait(.01):
            if (directory / "gate-decision.json").exists():
                action = read_json(directory / "gate-decision.json")["action"]
                if action == "approve":
                    atomic_write(directory / "received.pk3", pokemon(133))
                else:
                    write_json(directory / "gate-cancelled.json", {"cancelled": True})
                self.finished.set()
                return 0


class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "localhost")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-datetime.timedelta(minutes=1))
                .not_valid_after(now+datetime.timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
                .sign(key, hashes.SHA256()))
        cert_path, key_path = self.root/"cert.pem", self.root/"key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        self.relay = Relay(("127.0.0.1", 0), "a"*32)
        self.relay.socket = context.wrap_socket(self.relay.socket, server_side=True)
        self.server_thread = threading.Thread(target=self.relay.serve_forever, daemon=True)
        self.server_thread.start()
        trusted = ssl.create_default_context(cafile=str(cert_path))
        self.patch = patch("poketrader.remote.urlopen", lambda request, **kw: real_urlopen(request, context=trusted, **kw))
        self.patch.start()
        self.url = f"https://127.0.0.1:{self.relay.server_port}"
        self.a, self.b = self.root/"a.json", self.root/"b.json"
        room = configure(self.a, self.url, "a"*32, "source")
        configure(self.b, self.url, "a"*32, "switch", room)
        self.source = ManualRemote(self.a, self.root/"source-peer")
        self.radio = Radio()
        self.worker = SwitchWorker(self.b, self.root/"switch-peer", self.radio)
        self.service = Service(self.root/"saves", self.source)
        self.trade = "b"*32
        save_id, _ = self.service.upload(save())
        self.service.prepare(self.trade, save_id, 0)

    def tearDown(self):
        self.worker.close()
        self.source.stop()
        self.patch.stop()
        self.relay.shutdown()
        self.relay.server_close()
        self.server_thread.join()
        self.temp.cleanup()

    def sync(self):
        self.source.peer.exchange()
        self.worker.peer.exchange()
        self.source.peer.exchange()

    def pair(self):
        self.sync()
        self.assertTrue(self.source.peer.verified())
        self.assertTrue(self.worker.peer.verified())
        self.sync()

    def offer(self):
        self.pair()
        self.service.start(self.trade)
        self.service.state(self.trade)
        self.sync()
        self.worker.advance()
        deadline = time.monotonic()+3
        while not (self.worker.directory/"gate-offer.json").exists():
            if time.monotonic() > deadline: self.fail("Radio never offered")
            time.sleep(.01)
        self.worker.advance()
        self.sync()
        state = self.service.state(self.trade)
        self.sync()
        revision = self.worker.peer.values()[0]["proposal"]["revision"]
        self.assertEqual(state["state"], "running")
        self.assertEqual(self.source.peer.values()[0]["approval"], revision)
        self.assertEqual(self.worker.peer.values()[0]["approval"], revision)
        return revision

    def test_full_exchange_automatically_accepts_and_releases_verified_receipt(self):
        self.offer()
        self.worker.advance()
        self.assertTrue(self.radio.finished.wait(3))
        self.worker.radio.join(3)
        self.sync()
        self.assertEqual(self.service.state(self.trade)["state"], "ready")
        self.assertEqual(Save(self.service.result(self.trade)).pokemon(0).species, 133)
        self.service.applied(self.trade)
        self.sync()
        self.assertTrue(self.worker.peer.values()[1]["applied"])
        self.assertEqual(self.radio.calls, 1)
        self.assertNotIn("pokemon", json.dumps(self.relay.rooms))

    def test_completed_room_is_reused_without_new_config_or_controls(self):
        self.offer()
        self.worker.advance()
        self.assertTrue(self.radio.finished.wait(3))
        self.worker.radio.join(3)
        self.sync()
        self.assertEqual(self.service.state(self.trade)["state"], "ready")
        self.service.applied(self.trade)
        self.sync()

        next_trade = "c"*32
        save_id, _ = self.service.upload(save())
        self.service.prepare(next_trade, save_id, 0)
        self.service.start(next_trade)
        self.service.state(next_trade)
        self.radio.finished.clear()
        self.sync()
        self.worker.advance()
        deadline = time.monotonic()+3
        while not (self.worker.directory/"gate-offer.json").exists():
            if time.monotonic() > deadline: self.fail("Second exchange never offered")
            time.sleep(.01)
        self.worker.advance()
        self.sync()
        self.assertEqual(self.service.state(next_trade)["state"], "running")
        self.sync()
        self.worker.advance()
        self.assertTrue(self.radio.finished.wait(3))
        self.assertEqual(self.radio.calls, 2)

    def test_relay_restart_and_bridge_restart_do_not_relaunch(self):
        self.offer()
        self.worker.close()
        self.worker = SwitchWorker(self.b, self.root/"switch-peer", Radio())
        self.assertEqual(self.worker.peer.values()[0]["phase"], "uncertain")
        with self.relay.lock: self.relay.rooms.clear()
        self.sync()
        self.worker.advance()
        self.assertEqual(self.worker.backend.calls, 0)
        self.assertEqual(self.service.state(self.trade)["state"], "uncertain")

    def test_no_pokemon_payload_before_the_room_peer_is_pinned(self):
        self.service.start(self.trade)
        self.assertEqual(self.service.state(self.trade)["state"], "running")
        self.assertNotIn("offer", self.source.peer.values()[0])
        self.worker.advance()
        self.assertEqual(self.radio.calls, 0)
        self.sync()
        self.service.state(self.trade)
        self.assertIn("offer", self.source.peer.values()[0])

    def test_replayed_snapshot_cannot_restore_old_approval(self):
        self.pair()
        room = self.source.peer.config["room"]
        old = dict(self.relay.rooms[room]["switch"]["envelope"])
        self.worker.peer.update(approval="new-state")
        self.sync()
        with self.relay.lock:
            self.relay.rooms[room]["switch"]["envelope"] = old
        self.source.peer.exchange()
        self.assertEqual(self.source.peer.values()[1]["approval"], "new-state")

    def test_changed_offer_is_revalidated_and_accepted_automatically(self):
        revision = self.offer()
        write_json(self.worker.directory/"gate-offer.json", dict(revision="offer-2", pokemon=encode(pokemon(133))))
        self.worker.advance()
        self.sync()
        self.service.state(self.trade)
        self.assertEqual(self.source.peer.values()[0]["approval"], "offer-2")
        self.assertEqual(self.worker.peer.values()[0]["approval"], "offer-2")
        with self.assertRaises(Conflict): self.service.remote_action(self.trade, "approve", revision)
        self.assertFalse((self.worker.directory/"gate-decision.json").exists())

    def test_cancellation_declines_and_does_not_produce_save(self):
        self.offer()
        self.source.cancel()
        self.sync()
        self.worker.advance()
        self.assertTrue(self.radio.finished.wait(3))
        self.worker.radio.join(3)
        self.sync()
        self.assertEqual(self.service.state(self.trade)["state"], "cancelled")
        with self.assertRaises(Conflict): self.service.result(self.trade)

    def test_reject_trade_evolution_before_approval(self):
        self.offer()
        write_json(self.worker.directory/"gate-offer.json", dict(revision="bad", pokemon=encode(pokemon(64))))
        self.worker.advance()
        self.sync()
        self.assertIn("rejected", self.service.state(self.trade)["message"])
        with self.assertRaises(ValueError): self.source.approve("bad")

    def test_peer_identity_pin_and_https_requirement(self):
        self.pair()
        with self.assertRaises(ValueError):
            configure(self.root/"insecure.json", "http://127.0.0.1", "a"*32, "source")
        room = self.source.peer.config["room"]
        intruder_config = self.root/"intruder.json"
        configure(intruder_config, self.url, "a"*32, "switch", room)
        intruder = Peer(intruder_config, self.root/"intruder-peer")
        with self.assertRaises(HTTPError) as occupied:
            intruder.exchange()
        self.assertEqual(occupied.exception.code, 409)
        with self.relay.lock:
            self.relay.rooms[room]["switch"]["public"] = public_key(new_identity())
        with self.assertRaisesRegex(ValueError, "identity changed"):
            self.source.peer.exchange()

    def test_bridge_sends_an_explicit_user_agent(self):
        seen = {}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, _limit): return b'{}'
        def capture(request, **_):
            seen["agent"] = request.get_header("User-agent")
            return Response()
        with patch("poketrader.remote.urlopen", capture):
            self.source.peer.exchange()
        self.assertEqual(seen["agent"], "PokeTrader-Bridge/0.2")

    def test_room_change_persists_and_cannot_abandon_pinned_pairing(self):
        new_room = "d"*32
        self.worker.join(new_room)
        self.assertEqual(read_json(self.b)["room"], new_room)
        self.assertEqual(self.worker.directory.parent.name, new_room)
        self.worker.close()
        self.worker = SwitchWorker(self.b, self.root/"switch-peer", Radio())
        self.assertEqual(self.worker.peer.config["room"], new_room)
        self.worker.peer.update(verified=True)
        with self.assertRaises(ValueError): self.worker.join("e"*32)

if __name__ == "__main__": unittest.main()
