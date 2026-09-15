"""Offline integration checks against the installed pinned transport. No radio access."""
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from poketrader.backend import LiveBackend, UPSTREAM_REVISION
from poketrader.save import decode_box
from poketrader.upstream_runner import install_commit_writer, install_party_loader
from tests.fixtures import pokemon

upstream = Path(sys.argv[1] if len(sys.argv)>1 else ROOT/".deps/frlg-ldn-trade").resolve()
assert subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()==UPSTREAM_REVISION
sys.path.insert(0, str(upstream))
import frlgtrade

with tempfile.TemporaryDirectory() as temporary:
    directory = Path(temporary)
    backend = LiveBackend(upstream, directory/"unused.keys", "phy1")
    command = backend.command(directory, 0x12345678)
    parser = frlgtrade.build_parser()
    config = frlgtrade._build_run_config(parser, parser.parse_args(command[4:]))
    assert config.profile.name == "3DSLINK"
    install_party_loader(frlgtrade)
    install_commit_writer(frlgtrade, config)
    assert frlgtrade.args is config
    for pid in range(24):
        for ot in (pid, 12345678):
            offered = pokemon(pid=pid, ot=ot)
            (directory/"offered.pk3").write_bytes(offered)
            (directory/"companion.pk3").write_bytes(pokemon(1, pid=78))
            party = frlgtrade.runtime.load_party(config.plan.party_paths, lambda _:None)
            assert decode_box(party[1].box_bytes()) == offered
            assert party[1].party_bytes()[84] > 0
            assert party[1].party_bytes()[85] == 255
            engine = SimpleNamespace(received_mons=[party[1]])
            assert frlgtrade.save_received(engine, config, lambda _:None) == 1
            assert (directory/"received.pk3").read_bytes() == offered
print("Pinned upstream CLI, 48 explicit-format loads, party stats and durable receipt callback passed; no radio used.")
