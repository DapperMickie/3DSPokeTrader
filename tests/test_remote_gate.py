"""Optional adapter checks against the exact upstream checkout, without radio hardware."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

from poketrader.remote_gate import install
from poketrader.save import encode_box
from poketrader.storage import read_json, write_json
from .fixtures import pokemon


@unittest.skipUnless(os.environ.get("POKETRADER_TEST_UPSTREAM"), "Set POKETRADER_TEST_UPSTREAM to the pinned checkout")
class GateTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.environ["POKETRADER_TEST_UPSTREAM"])
        self.trade = importlib.import_module("frlgsim.trade")
        self.mon = importlib.import_module("frlgsim.mon")
        self.originals = {name: getattr(self.trade.TradeEngine, name)
                          for name in ("_run_confirm", "tick", "_on_linkcmd")}
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        install(SimpleNamespace(trade=self.trade), self.root)
        party = [self.mon.Mon(encode_box(pokemon(25))+bytes(20)),
                 self.mon.Mon(encode_box(pokemon(133))+bytes(20))]
        self.engine = self.trade.TradeEngine(party)
        self.engine._host_party[:100] = encode_box(pokemon(133))+bytes(20)
        self.engine._host_party[100:200] = encode_box(pokemon(25))+bytes(20)
        self.engine.state = self.trade.S5_SELECT

    def tearDown(self):
        for name, method in self.originals.items(): setattr(self.trade.TradeEngine, name, method)
        sys.path.pop(0)
        self.temp.cleanup()

    def test_waits_for_exact_revision_while_ticks_continue(self):
        self.engine._on_linkcmd(self.trade.SET_MONS_TO_TRADE, 0)
        offer = read_json(self.root/"gate-offer.json")
        self.assertFalse(self.engine._confirmed)
        for _ in range(10): self.engine.tick()
        self.assertFalse(self.engine._confirmed)
        write_json(self.root/"gate-decision.json", dict(revision="stale", action="approve"))
        self.engine._remote_check = 0
        self.engine.tick()
        self.assertFalse(self.engine._confirmed)
        write_json(self.root/"gate-decision.json", dict(revision=offer["revision"], action="approve"))
        self.engine._remote_check = 0
        self.engine.tick()
        self.assertTrue(self.engine._confirmed)

    def test_early_start_rejected(self):
        with self.assertRaises(ValueError): self.engine._on_linkcmd(self.trade.START_TRADE, 0)

    def test_changed_record_in_same_slot_invalidates_approval(self):
        self.engine._on_linkcmd(self.trade.SET_MONS_TO_TRADE, 0)
        first = read_json(self.root/"gate-offer.json")
        write_json(self.root/"gate-decision.json", dict(revision=first["revision"], action="approve"))
        self.engine._host_party[:100] = encode_box(pokemon(25))+bytes(20)
        self.engine.tick()
        self.assertFalse(self.engine._confirmed)
        self.assertNotEqual(first["revision"], read_json(self.root/"gate-offer.json")["revision"])

    def test_reselection_invalidates_the_approval_token(self):
        self.engine._on_linkcmd(self.trade.SET_MONS_TO_TRADE, 0)
        first = read_json(self.root/"gate-offer.json")
        self.engine._on_linkcmd(self.trade.PLAYER_CANCEL_TRADE, 0)
        self.assertTrue(read_json(self.root/"gate-offer.json")["cancelled"])
        self.engine._on_linkcmd(self.trade.SET_MONS_TO_TRADE, 1)
        second = read_json(self.root/"gate-offer.json")
        self.assertNotEqual(first["revision"], second["revision"])
        self.assertNotEqual(first["pokemon"], second["pokemon"])

    def test_decline_cannot_later_commit(self):
        self.engine._on_linkcmd(self.trade.SET_MONS_TO_TRADE, 0)
        offer = read_json(self.root/"gate-offer.json")
        write_json(self.root/"gate-decision.json", dict(revision=offer["revision"], action="decline"))
        self.engine.tick()
        self.assertTrue(self.engine.cancelled)
        with self.assertRaises(ValueError): self.engine._on_linkcmd(self.trade.START_TRADE, 0)


if __name__ == "__main__": unittest.main()
