from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
import os
import sys
import time

from poketrader.backend import DemoBackend, LiveBackend
from poketrader.save import Save
from poketrader.service import Service, Conflict
from poketrader.storage import atomic_write, read_json, write_json
from .fixtures import save, pokemon

TRADE = "a"*32


class ControlledBackend:
    label = "TEST"
    def __init__(self, receipt=None, code=0):
        self.calls=0; self.receipt=receipt; self.code=code
        self.gate=threading.Event()
    def preflight(self): pass
    def run(self, directory, trainer_id):
        self.calls+=1
        self.gate.wait(5)
        if self.receipt is not None: atomic_write(directory/"received.pk3",self.receipt)
        return self.code


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.backend=ControlledBackend(pokemon(133))
        self.service=Service(self.root,self.backend)
        self.save_id,_=self.service.upload(save())
        self.service.prepare(TRADE,self.save_id,0)
    def tearDown(self):
        self.backend.gate.set()
        for thread in self.service.threads: thread.join(5)
        self.temp.cleanup()

    def finish(self):
        self.backend.gate.set()
        for thread in self.service.threads: thread.join(5)

    def test_duplicate_start_race_runs_radio_once(self):
        with ThreadPoolExecutor(8) as pool:
            list(pool.map(lambda _:self.service.start(TRADE),range(20)))
        self.finish()
        self.assertEqual(self.backend.calls,1)
        self.assertEqual(self.service.state(TRADE)["state"],"received")
        self.service.start(TRADE)
        self.assertEqual(self.backend.calls,1)

    def test_confirmation_and_result_are_idempotent(self):
        self.service.start(TRADE); self.finish()
        first=self.service.confirm(TRADE)
        self.assertEqual(first,self.service.confirm(TRADE))
        result=self.service.result(TRADE)
        self.assertEqual(Save(result).pokemon(0).species,133)
        self.service.applied(TRADE)
        self.assertEqual(result,self.service.result(TRADE))
        self.assertEqual(self.service.state(TRADE)["state"],"applied")

    def test_cannot_download_or_confirm_before_receipt(self):
        with self.assertRaises(Conflict): self.service.result(TRADE)
        with self.assertRaises(Conflict): self.service.confirm(TRADE)

    def test_receipt_survives_nonzero_exit(self):
        self.backend.code=1; self.service.start(TRADE); self.finish()
        self.assertEqual(self.service.state(TRADE)["state"],"received")

    def test_no_receipt_locks_bridge_and_does_not_retry(self):
        self.backend.receipt=None; self.service.start(TRADE); self.finish()
        self.assertEqual(self.service.state(TRADE)["state"],"uncertain")
        other="b"*32; self.service.prepare(other,self.save_id,0)
        with self.assertRaises(Conflict): self.service.start(other)
        self.service.start(TRADE)
        self.assertEqual(self.backend.calls,1)
        self.service.resolve_no_trade(TRADE)
        self.assertEqual(self.service.state(TRADE)["state"],"cancelled")

    def test_restart_recovers_receipt_but_never_starts_radio(self):
        directory=self.service.directory(TRADE)
        state=self.service.state(TRADE); state["state"]="running"
        write_json(directory/"state.json",state)
        atomic_write(directory/"received.pk3",pokemon(133))
        restarted=Service(self.root,self.backend)
        self.assertEqual(restarted.state(TRADE)["state"],"received")
        self.assertEqual(self.backend.calls,0)

    def test_restart_without_receipt_is_uncertain(self):
        path=self.service.directory(TRADE)/"state.json"
        state=read_json(path); state["state"]="running"; write_json(path,state)
        restarted=Service(self.root,self.backend)
        self.assertEqual(restarted.state(TRADE)["state"],"uncertain")

    def test_invalid_receipt_cannot_be_imported(self):
        self.backend.receipt=b"invalid"; self.service.start(TRADE); self.finish()
        self.assertEqual(self.service.state(TRADE)["state"],"uncertain")

    def test_unsupported_receipt_preserved_for_manual_recovery(self):
        self.backend.receipt=pokemon(egg=True); self.service.start(TRADE); self.finish()
        self.assertEqual(self.service.confirm(TRADE)["state"],"import_blocked")
        self.assertTrue((self.service.directory(TRADE)/"received.pk3").is_file())

    def test_path_traversal_and_transaction_reuse_rejected(self):
        with self.assertRaises(ValueError): self.service.state("../../state")
        with self.assertRaises(Conflict): self.service.prepare(TRADE,self.save_id,1)

    def test_result_tamper_is_detected(self):
        self.service.start(TRADE); self.finish(); self.service.confirm(TRADE)
        atomic_write(self.service.directory(TRADE)/"result.sav",save())
        with self.assertRaises(Conflict): self.service.result(TRADE)

    def test_live_command_never_interpolates_shell_input(self):
        backend=LiveBackend(Path("repo with spaces"),Path("private key.keys"),"phy1")
        command=backend.command(self.root,0x12345678)
        self.assertIsInstance(command,list)
        self.assertEqual(command[command.index("--slot")+1],"1")
        self.assertEqual(command[command.index("--trades")+1],"1")
        self.assertEqual(command[command.index("--out-format")+1],"pk3")

    @unittest.skipIf(os.name == "nt", "Live process shutdown uses POSIX signals")
    def test_shutdown_reaps_child_and_preserves_uncertain_state(self):
        class ProcessBackend(LiveBackend):
            def preflight(self): pass
            def command(self, directory, trainer_id):
                return [sys.executable, "-c", "import time; time.sleep(60)"]
        backend=ProcessBackend(self.root,self.root/"unused.keys","phy1")
        self.service.backend=backend
        self.service.start(TRADE)
        deadline=time.monotonic()+5
        while backend.process is None and time.monotonic()<deadline: time.sleep(0.01)
        child=backend.process
        self.assertIsNotNone(child)
        self.service.close()
        self.assertIsNotNone(child.poll())
        self.assertEqual(self.service.state(TRADE)["state"],"uncertain")
        with self.assertRaises(Conflict): self.service.start(TRADE)


if __name__ == "__main__": unittest.main()
