from __future__ import annotations
import argparse
from contextlib import contextmanager
from pathlib import Path
import os
import secrets
import sys

from .backend import DemoBackend, LiveBackend
from .save import Save
from .server import Server
from .service import Service
from .storage import atomic_write, read_json


@contextmanager
def exclusive(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def main(argv=None):
    parser = argparse.ArgumentParser(description="3DS FRLG save exchange bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Validate a raw FRLG save without changing it")
    inspect.add_argument("save", type=Path)
    inspect.add_argument("--box", type=int, default=1, choices=range(1, 15))
    pairing = sub.add_parser("pair", help="Write the SD-card bridge.cfg with a new token")
    pairing.add_argument("--host", required=True, help="PC's LAN IPv4 address")
    pairing.add_argument("--port", type=int, default=8765)
    pairing.add_argument("--output", type=Path, default=Path("bridge.cfg"))
    serve = sub.add_parser("serve")
    serve.add_argument("--data", type=Path, default=Path("bridge-data"))
    serve.add_argument("--config", type=Path, default=Path("bridge.cfg"))
    serve.add_argument("--bind", default="0.0.0.0")
    mode = serve.add_mutually_exclusive_group(required=True)
    mode.add_argument("--upstream", type=Path)
    mode.add_argument("--demo-receive", type=Path, help="Rehearsal only: receive this decrypted 80-byte PK3")
    serve.add_argument("--keys", type=Path, default=Path("~/.switch/prod.keys"))
    serve.add_argument("--phy", default="phy1")
    serve.add_argument("--python", default=sys.executable, help="Python interpreter with upstream dependencies installed")
    resolve = sub.add_parser("resolve-no-trade", help="Unlock an uncertain transaction after manually checking both consoles")
    resolve.add_argument("trade_id")
    resolve.add_argument("--data", type=Path, default=Path("bridge-data"))
    resolve.add_argument("--neither-side-traded", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            save = Save(args.save.read_bytes())
            print(f"FRLG | {save.trainer} | TID {save.trainer_id & 65535:05d}")
            print(save.warning or "Both save slots valid.")
            print(save.box_lines(args.box-1), end="")
        elif args.command == "pair":
            import ipaddress
            ipaddress.IPv4Address(args.host)
            if not 1 <= args.port <= 65535:
                raise ValueError("Port is out of range.")
            if args.output.exists():
                raise ValueError("Config already exists. Choose another output path to avoid breaking pairing.")
            atomic_write(args.output, f"{args.host}\n{args.port}\n{secrets.token_hex(16)}\n".encode())
            print(f"Wrote {args.output}. Copy to sdmc:/3ds/PokeTrader/bridge.cfg and use the same file on the bridge.")
        elif args.command == "serve":
            fields = args.config.read_text().splitlines()
            if len(fields) != 3 or len(fields[2]) != 32 or any(c not in "0123456789abcdef" for c in fields[2]):
                raise ValueError("Invalid pairing config; run the pair command.")
            port, token = int(fields[1]), fields[2]
            backend = (DemoBackend(args.demo_receive.read_bytes()) if args.demo_receive else
                       LiveBackend(args.upstream, args.keys, args.phy, args.python))
            backend.preflight()
            with exclusive(args.data):
                service = Service(args.data, backend)
                server = Server((args.bind, port), service, token)
                print(f"{backend.label}: bridge listening on {args.bind}:{port}", flush=True)
                try:
                    server.serve_forever()
                finally:
                    server.server_close()
                    service.close()
        else:
            # Acquire the same lock as serve; never reconcile a running service.
            with exclusive(args.data):
                service = Service(args.data, None)
                print(service.resolve_no_trade(args.trade_id)["message"])
        return 0
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Bridge stopped. Unfinished trades require recovery; do not automatically repeat them.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
