import asyncio
from types import SimpleNamespace
import unittest

from poketrader.upstream_runner import install_scan_dwell


class ScanDwellTests(unittest.TestCase):
    def test_default_dwell_is_extended_but_explicit_value_is_preserved(self):
        calls = []

        async def scan(*args, **kwargs):
            calls.append(kwargs)
            return []

        module = SimpleNamespace(scan=scan)
        install_scan_dwell(module, 2.0)
        asyncio.run(module.scan("keys", phyname="phy0"))
        asyncio.run(module.scan("keys", dwell_time=4.0))
        self.assertEqual(calls[0]["dwell_time"], 2.0)
        self.assertEqual(calls[1]["dwell_time"], 4.0)


if __name__ == "__main__":
    unittest.main()
