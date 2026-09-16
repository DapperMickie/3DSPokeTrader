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
    mode.add_argument("--remote", type=Path, help="Optional source remote config; local-only remains default")
    serve.add_argument("--experimental-remote", action="store_true")
    serve.add_argument("--keys", type=Path, default=Path("~/.switch/prod.keys"))
    serve.add_argument("--phy", default="phy1")
    serve.add_argument("--python", default=sys.executable, help="Python interpreter with upstream dependencies installed")
    resolve = sub.add_parser("resolve-no-trade", help="Unlock an uncertain transaction after manually checking both consoles")
    resolve.add_argument("trade_id")
    resolve.add_argument("--data", type=Path, default=Path("bridge-data"))
    resolve.add_argument("--neither-side-traded", action="store_true", required=True)
    relay = sub.add_parser("relay", help="Run the optional self-hosted relay behind HTTPS")
    relay.add_argument("--credential-file", type=Path, default=Path("relay-data/relay-credential"))
    relay.add_argument("--bind", default="127.0.0.1")
    relay.add_argument("--port", type=int, default=8780)
    remote = sub.add_parser("remote-config", help="Create a private room config for one exchange")
    remote.add_argument("--relay", required=True)
    remote.add_argument("--credential-file", type=Path, required=True)
    remote.add_argument("--role", choices=("source", "switch", "switch-a", "switch-b",
                                           "source-a", "source-b"), required=True)
    remote.add_argument("--room", help="Room code from the source player; Switch users can also join from the browser")
    remote.add_argument("--output", type=Path, required=True)
    switch = sub.add_parser("remote-switch", help="Automated trusted-room Switch bridge")
    switch.add_argument("--remote", type=Path, required=True)
    switch.add_argument("--data", type=Path, default=Path("remote-switch-data"))
    switch.add_argument("--upstream", type=Path, required=True)
    switch.add_argument("--keys", type=Path, default=Path("~/.switch/prod.keys"))
    switch.add_argument("--phy", default="phy1")
    switch.add_argument("--python", default=sys.executable)
    switch.add_argument("--bootstrap-save", type=Path,
                        help="FRLG save supplying two temporary party Pokemon for a Switch-to-Switch room")
    # Retained as ignored compatibility options for existing launch scripts.
    switch.add_argument("--bind", default="127.0.0.1", help=argparse.SUPPRESS)
    switch.add_argument("--port", type=int, default=8766, help=argparse.SUPPRESS)
    switch.add_argument("--experimental-remote", action="store_true", required=True)
    reconcile = sub.add_parser("remote-resolve-no-trade", help="Reconcile an uncertain remote exchange after checking both consoles")
    reconcile.add_argument("--remote", type=Path, required=True)
    reconcile.add_argument("--data", type=Path, required=True)
    reconcile.add_argument("--neither-side-traded", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "relay":
            from .relay import Relay
            if not args.credential_file.exists():
                atomic_write(args.credential_file, secrets.token_hex(32).encode())
                try:
                    args.credential_file.chmod(0o600)
                except OSError:
                    pass
                print(f"Generated relay credential in {args.credential_file}.", flush=True)
            server = Relay((args.bind, args.port), args.credential_file.read_text().strip())
            print(f"Relay listening on {args.bind}:{args.port}; HTTPS reverse proxy required.", flush=True)
            try:
                server.serve_forever()
            finally:
                server.server_close()
        elif args.command == "remote-config":
            from .remote import configure
            room = configure(args.output, args.relay, args.credential_file.read_text().strip(), args.role, args.room)
            print(f"Room code: {room}. Share the code with your friend. Keep the config private for recovery.")
        elif args.command == "remote-resolve-no-trade":
            from .remote import Peer
            with exclusive(args.data):
                remote_config = read_json(args.remote)
                peer = Peer(args.remote, args.data / "rooms" / remote_config["room"])
                if peer.config["role"] != "switch":
                    raise ValueError("Reconcile on the Switch bridge")
                local, _ = peer.values()
                if local.get("phase") not in ("uncertain", "running", "offer", "committing"):
                    raise ValueError("Only an interrupted exchange can be reconciled")
                if (peer.root / "exchange/received.pk3").exists():
                    raise ValueError("A receipt exists; inspect it instead of declaring no trade")
                peer.update(phase="cancelled", approval=None, message="Operator checked both consoles: no trade occurred.")
                print("Recorded no trade. Restart the Switch bridge to notify the source bridge; use a new room for another exchange.")
        elif args.command == "remote-switch":
            from .remote import SwitchPairWorker, SwitchWorker
            with exclusive(args.data):
                backend = LiveBackend(args.upstream, args.keys, args.phy, args.python)
                backend.preflight()
                role = read_json(args.remote)["role"]
                if role in ("switch-a", "switch-b"):
                    if not args.bootstrap_save:
                        raise ValueError("Switch-to-Switch rooms require --bootstrap-save")
                    worker = SwitchPairWorker(args.remote, args.data, backend, args.bootstrap_save)
                    print(f"Switch-to-Switch room {worker.peer.config['room']}: waiting for the other bridge.", flush=True)
                else:
                    worker = SwitchWorker(args.remote, args.data, backend)
                    print(f"Trusted room {worker.peer.config['room']}: waiting for the 3DS bridge. No web controls are required.", flush=True)
                try:
                    worker.run()
                finally:
                    worker.close()
        elif args.command == "inspect":
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
            with exclusive(args.data):
                if args.remote:
                    if not args.experimental_remote:
                        raise ValueError("Remote hardware validation is incomplete; use --experimental-remote to opt in")
                    from .remote import RemoteBackend, SourcePairBackend
                    role = read_json(args.remote)["role"]
                    backend_type = SourcePairBackend if role in ("source-a", "source-b") else RemoteBackend
                    backend = backend_type(args.remote, args.data / "remote")
                else:
                    backend = (DemoBackend(args.demo_receive.read_bytes()) if args.demo_receive else
                               LiveBackend(args.upstream, args.keys, args.phy, args.python))
                backend.preflight()
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
    except ModuleNotFoundError as exc:
        if exc.name == "cryptography":
            print("Remote mode requires: python -m pip install '.[remote]'", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
