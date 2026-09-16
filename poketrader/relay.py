"""Bounded in-memory relay. Run behind HTTPS; never receives plaintext trade data."""
from __future__ import annotations

import hmac
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOM = re.compile(r"^[0-9a-f]{32}$")
MAX_BODY = 16384


class Relay(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, credential, max_rooms=100, ttl=600):
        if len(credential) < 32:
            raise ValueError("Relay credential must contain at least 32 characters")
        self.credential, self.max_rooms, self.ttl = credential, max_rooms, ttl
        self.rooms = {}
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(64)
        super().__init__(address, RelayHandler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class RelayHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass

    def reply(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not hmac.compare_digest(self.headers.get("Authorization", ""),
                                   "Bearer " + self.server.credential):
            self.reply(401, {"error": "Invalid relay credential"})
            return
        try:
            if self.path != "/v1/exchange" or self.headers.get("Transfer-Encoding"):
                raise ValueError("Invalid request")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not 0 < int(lengths[0]) <= MAX_BODY:
                raise ValueError("Invalid request length")
            data = self.rfile.read(int(lengths[0]))
            if len(data) != int(lengths[0]):
                raise ValueError("Interrupted request")
            value = json.loads(data)
            room, role = value["room"], value["role"]
            if not ROOM.fullmatch(room) or role not in ("source", "switch"):
                raise ValueError("Invalid room or role")
            public, lease = value["public"], value["lease"]
            if not isinstance(public, str) or len(public) != 44 or not ROOM.fullmatch(lease):
                raise ValueError("Invalid identity")
            now = time.monotonic()
            with self.server.lock:
                self.server.rooms = {k: v for k, v in self.server.rooms.items()
                                     if now - v["touched"] < self.server.ttl}
                if room not in self.server.rooms:
                    if len(self.server.rooms) >= self.server.max_rooms:
                        self.reply(503, {"error": "Relay room limit reached"})
                        return
                    self.server.rooms[room] = {"touched": now}
                state = self.server.rooms[room]
                old = state.get(role)
                if old and (old["lease"] != lease or old["public"] != public):
                    self.reply(409, {"error": "Room role already occupied"})
                    return
                state["touched"] = now
                state[role] = {"lease": lease, "public": public,
                               "envelope": value.get("envelope")}
                other = state.get("switch" if role == "source" else "source")
                answer = ({"public": other["public"], "envelope": other["envelope"]}
                          if other else {})
            self.reply(200, answer)
        except (ValueError, KeyError, TypeError):
            self.reply(400, {"error": "Malformed exchange"})
        except (OSError, TimeoutError):
            self.close_connection = True
