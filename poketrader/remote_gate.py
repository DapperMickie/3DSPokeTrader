"""Explicit remote-only approval adapter for the pinned upstream engine.

All network work stays outside the radio loop. Never assumes receipt == console save.
"""
import base64
import secrets
import time

from .storage import write_json, read_json
from .save import Pokemon


def install(module, directory):
    engine_class = module.trade.TradeEngine
    original_confirm = engine_class._run_confirm
    original_tick = engine_class.tick
    original_command = engine_class._on_linkcmd

    def offered(engine):
        from frlgsim.mon import Mon, to_decrypted
        offset = (engine.host_cursor % 6) * 100
        data = to_decrypted(Mon(bytes(engine._host_party[offset:offset+100])).box_bytes())
        Pokemon(data).check_tradeable()
        return base64.b64encode(data).decode("ascii")

    def confirm(engine):
        if getattr(engine, "_remote_allowed", False):
            return original_confirm(engine)
        if getattr(engine, "_remote_offer", None) is None:
            engine._remote_offer = dict(revision=secrets.token_hex(16),
                pokemon=offered(engine))
            write_json(directory / "gate-offer.json", engine._remote_offer)

    def tick(engine):
        now = time.monotonic()
        if (getattr(engine, "_remote_offer", None) and not getattr(engine, "_remote_allowed", False)
                and now >= getattr(engine, "_remote_check", 0)):
            engine._remote_check = now + .2
            if offered(engine) != engine._remote_offer["pokemon"]:
                engine._remote_offer = None
                confirm(engine)
            try:
                decision = read_json(directory / "gate-decision.json")
            except FileNotFoundError:
                decision = {}
            if decision.get("revision") == engine._remote_offer["revision"]:
                if decision.get("action") == "approve":
                    engine._remote_allowed = True
                    original_confirm(engine)
                elif decision.get("action") == "decline":
                    engine.decline = True
                    original_confirm(engine)
        return original_tick(engine)

    def command(engine, cmd, cursor):
        trade = module.trade
        if cmd in (trade.START_TRADE, trade.CONFIRM_FINISH_TRADE) and not getattr(engine, "_remote_allowed", False):
            raise ValueError("Switch attempted commitment before remote approval")
        if cmd in (trade.START_TRADE, trade.CONFIRM_FINISH_TRADE) and offered(engine) != engine._remote_offer["pokemon"]:
            raise ValueError("Switch offer changed after approval; inspect console")
        if cmd == trade.SET_MONS_TO_TRADE and getattr(engine, "_remote_offer", None):
            if cursor != engine.host_cursor:
                if getattr(engine, "_remote_allowed", False):
                    raise ValueError("Switch selection changed after approval; inspect console")
                engine._remote_offer = None
                engine.host_cursor = cursor
                confirm(engine)
        if cmd in (trade.PLAYER_CANCEL_TRADE, trade.PARTNER_CANCEL_TRADE, trade.BOTH_CANCEL_TRADE):
            if getattr(engine, "_remote_allowed", False) and not engine.commits:
                raise ValueError("Switch cancelled after approval; inspect console before recovery")
            if not getattr(engine, "_remote_allowed", False):
                engine._remote_offer = None
                # Invalidate stale UI approvals immediately on cancellation/reselection.
                write_json(directory / "gate-offer.json", dict(revision=secrets.token_hex(16), cancelled=True))
                if cmd == trade.BOTH_CANCEL_TRADE:
                    write_json(directory / "gate-cancelled.json", {"cancelled": True})
        return original_command(engine, cmd, cursor)

    engine_class._run_confirm = confirm
    engine_class.tick = tick
    engine_class._on_linkcmd = command
