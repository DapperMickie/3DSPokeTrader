"""Authenticated LAN controls for the Switch player. No relay credentials in the browser."""
import hmac
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .remote_crypto import decode
from .save import Pokemon
from .service import trade_art


class Controls(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, worker, token):
        self.worker, self.token = worker, token
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass

    def reply(self, status, body, content="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + self.server.token)

    def do_GET(self):
        if self.path == "/":
            self.reply(200, Path(__file__).with_name("remote.html").read_bytes(), "text/html; charset=utf-8")
            return
        if not self.authorized():
            self.reply(401, {"error": "Enter the local control token"})
            return
        if self.path == "/art.bin":
            path = Path(__file__).with_name("art.bin")
            if not path.exists():
                path = Path(__file__).resolve().parent.parent / "3ds/romfs/ui/art.bin"
            if not path.exists():
                self.reply(404, {})
                return
            self.reply(200, path.read_bytes(), "application/octet-stream")
            return
        if self.path != "/status":
            self.reply(404, {})
            return
        peer = self.server.worker.peer
        local, remote = peer.values()
        def mon(value):
            if not value:
                return None
            pokemon = Pokemon(decode(value))
            return {"summary": pokemon.summary, "art": trade_art(pokemon)}
        self.reply(200, dict(room=peer.config["room"], can_join=self.server.worker.can_join(), phase=local.get("phase", "pairing"),
            phrase=peer.channel.phrase if peer.channel else "", verified=local.get("verified"),
            both_verified=peer.verified(), error=peer.error, message=local.get("message", ""),
            revision=local.get("proposal", {}).get("revision", ""),
            can_approve=(local.get("phase") == "offer" and remote.get("validated") == local.get("proposal", {}).get("revision")),
            approved=bool(local.get("approval")), friend_approved=bool(remote.get("approval")),
            applied=remote.get("applied", False),
            outgoing=mon(local.get("proposal", {}).get("pokemon")), incoming=mon(remote.get("offer"))))

    def do_POST(self):
        if not self.authorized():
            self.reply(401, {"error": "Invalid local control token"})
            return
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1 or not 0 < int(lengths[0]) <= 1024:
                raise ValueError("Invalid request length")
            data = json.loads(self.rfile.read(int(lengths[0])))
            worker = self.server.worker
            with worker.control_lock:
                if self.path != "/join" and data.get("room") != worker.peer.config["room"]:
                    raise ValueError("Room changed. Refresh before taking action")
                if self.path == "/join":
                    worker.join(data["room"])
                elif self.path == "/verify":
                    worker.peer.verify(data["revision"])
                elif self.path == "/approve":
                    worker.approve(data["revision"])
                elif self.path == "/cancel":
                    worker.cancel()
                elif self.path == "/saved":
                    worker.saved()
                else:
                    raise ValueError("Unknown action")
            self.reply(200, {"ok": True})
        except (ValueError, KeyError, TypeError) as exc:
            self.reply(409, {"error": str(exc)})
