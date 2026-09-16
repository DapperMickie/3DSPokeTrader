"""Small compatibility wrapper for the pinned upstream revision.

Its run_live() references global `args` when saving at commit, although args is
local to main(). Expose the expected TradeRunConfig and replace save_received
with a durable writer. No packet/state-machine code is changed or copied.
"""
from __future__ import annotations
import importlib
from pathlib import Path
import sys
import os

from .save import Pokemon, encode_box
from .storage import atomic_write


def install_commit_writer(module, config):
    module.args = config

    def save_received(engine, run_config, log):
        mons = engine.received_mons or ([engine.received_mon] if engine.received_mon else [])
        if not mons:
            return 0
        if len(mons) != 1 or run_config.plan.trades != 1:
            raise ValueError("This bridge supports exactly one trade per transaction.")
        from frlgsim.mon import to_decrypted
        data = to_decrypted(mons[0].box_bytes())
        Pokemon(data)  # Validate before acknowledging a persisted receipt.
        atomic_write(Path(run_config.plan.output_path), data)
        return 1

    module.save_received = save_received


def install_party_loader(module):
    def load_party(paths, log):
        from frlgsim.mon import Mon
        from frlgsim.stats import build_party_tail
        party = []
        for path in paths:
            data = Path(path).read_bytes()
            Pokemon(data).check_tradeable()
            tail = build_party_tail(data)
            if tail is None or len(tail) != 20:
                raise ValueError("Upstream could not calculate party stats for the selected Pokemon.")
            # Inputs are explicitly canonical PK3. Avoid upstream's checksum-based
            # format guess, which is ambiguous for some personality/trainer keys.
            party.append(Mon(encode_box(data) + tail))
        return party
    module.runtime.load_party = load_party


def install_scan_dwell(ldn_module, seconds=2.0):
    """Give USB/IP radios enough time to receive an LDN action frame."""
    original = ldn_module.scan

    async def scan(*args, **kwargs):
        kwargs.setdefault("dwell_time", seconds)
        return await original(*args, **kwargs)

    ldn_module.scan = scan


def main():
    upstream = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(upstream))
    module = importlib.import_module("frlgtrade")
    parser = module.build_parser()
    args = parser.parse_args(sys.argv[2:])
    config = module._build_run_config(parser, args)
    import ldn
    install_scan_dwell(ldn)
    install_commit_writer(module, config)
    install_party_loader(module)
    if os.environ.get("POKETRADER_REMOTE_GATE"):
        from .remote_gate import install
        install(module, Path(os.environ["POKETRADER_REMOTE_GATE"]))
    return module.main(sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())
