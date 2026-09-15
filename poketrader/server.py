"""Small authenticated HTTP/1.0 API used by the 3DS client.

Text responses use UTF-8 newline-separated fields. Only saves/results are binary.
The bridge belongs on a private LAN; this is not an Internet-facing service.
"""
from __future__ import annotations
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .save import SAVE_SIZE
from .service import Conflict


def lines(*values):
    return ("\n".join(str(v).replace("\r", " ").replace("\n", " ") for v in values)+"\n").encode()


def state_body(state):
    return lines(state["state"], state["message"], state["received"], state["mode"],
                 state.get("result_sha256", ""))


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, service, token):
        self.service = service
        self.token = token
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "PokeTrader/0.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, *_args):
        pass  # Do not log paths, auth headers or save contents.

    def respond(self, status, body, binary=False):
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream" if binary else "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def dispatch(self, method):
        expected = "Bearer " + self.server.token
        if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
            self.respond(401, lines("Bridge pairing token is incorrect."))
            return
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Chunked requests are not supported.")
            raw_lengths = self.headers.get_all("Content-Length", [])
            if len(raw_lengths) > 1:
                raise ValueError("Duplicate request lengths.")
            length = int(raw_lengths[0]) if raw_lengths else 0
            if not 0 <= length <= SAVE_SIZE:
                self.respond(413, lines("Request is too large."))
                return
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Upload was interrupted.")
            path = urlsplit(self.path).path.strip("/").split("/")
            service = self.server.service
            if method == "GET" and path == ["v1", "health"]:
                self.respond(200, lines("PokeTrader/1", service.backend.label))
            elif method == "POST" and path == ["v1", "saves"]:
                save_id, save = service.upload(body)
                self.respond(200, lines(save_id, "FireRed / LeafGreen", save.trainer,
                                        save.trainer_id & 65535, save.warning, service.backend.label))
            elif method == "GET" and len(path) == 5 and path[:2] == ["v1", "saves"] and path[3] == "boxes":
                self.respond(200, service.save(path[2]).box_lines(int(path[4])).encode())
            elif method == "GET" and len(path) == 6 and path[:2] == ["v1", "saves"] and path[3] == "boxes" and path[5] == "details":
                self.respond(200, service.save(path[2]).box_details(int(path[4])).encode())
            elif len(path) >= 3 and path[:2] == ["v1", "trades"]:
                trade_id = path[2]
                if method == "PUT" and len(path) == 3:
                    fields = body.decode("ascii").splitlines()
                    if len(fields) != 2:
                        raise ValueError("Expected save ID and box slot.")
                    state = service.prepare(trade_id, fields[0], int(fields[1]))
                    self.respond(200, state_body(state))
                elif method == "GET" and len(path) == 3:
                    self.respond(200, state_body(service.state(trade_id)))
                elif method == "GET" and path[3:] == ["result"]:
                    self.respond(200, service.result(trade_id), binary=True)
                elif method == "POST" and path[3:] in (["start"], ["confirm"], ["applied"]):
                    if body:
                        raise ValueError("This request does not accept a body.")
                    operation = {"start": service.start, "confirm": service.confirm, "applied": service.applied}[path[3]]
                    self.respond(200, state_body(operation(trade_id)))
                else:
                    self.respond(404, lines("Unknown endpoint."))
            else:
                self.respond(404, lines("Unknown endpoint."))
        except Conflict as exc:
            self.respond(409, lines(exc))
        except (ValueError, UnicodeError) as exc:
            self.respond(400, lines(exc))
        except FileNotFoundError:
            self.respond(404, lines("Save or transaction not found."))
        except (TimeoutError, ConnectionError):
            self.close_connection = True
        except OSError:
            self.respond(500, lines("Bridge storage or process error. Check the PC and retained transaction files."))
