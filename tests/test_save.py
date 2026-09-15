import struct
import unittest
from poketrader.save import (Save, SaveError, Pokemon, encode_box, decode_box,
                            pokemon_checksum, section_checksum, SIZES, u32)
from .fixtures import save, pokemon


class SaveTests(unittest.TestCase):
    def test_ui_metadata_is_read_only_and_marks_eligibility(self):
        original = save(offered=pokemon(pid=0, ot=0))
        parsed = Save(original)
        rows = [line.split("\t") for line in parsed.box_details(0).splitlines()]
        self.assertEqual(len(rows), 30)
        self.assertTrue(all(len(row) == 14 for row in rows))
        self.assertEqual(rows[0][:9], ["0", "25", "1", "1", "10", "1", "ELECTRIC", "ELECTRIC", "Pikachu"])
        self.assertEqual(rows[0][12], "Hardy")
        self.assertEqual(rows[1][5], "0")
        self.assertEqual(parsed.pokemon(0).pk3, pokemon(pid=0, ot=0))
        for offered in (pokemon(egg=True), pokemon(item=121)):
            row = Save(save(offered=offered)).box_details(0).splitlines()[0].split("\t")
            self.assertEqual(row[3], "0")

    def test_growth_curve_level_100_values(self):
        from poketrader.save import experience_at
        expected = {"MEDIUM_FAST":1000000, "FAST":800000, "SLOW":1250000,
                    "MEDIUM_SLOW":1059860, "ERRATIC":600000, "FLUCTUATING":1640000}
        for curve, maximum in expected.items():
            self.assertEqual(experience_at(curve, 100), maximum)
            levels = [experience_at(curve, n) for n in range(1, 101)]
            self.assertEqual(levels, sorted(set(levels)))

    def test_all_shuffles_including_zero_xor_key(self):
        for pid in range(24):
            for ot in (pid, 0xABCDEF12):
                pk3 = pokemon(pid=pid, ot=ot)
                self.assertEqual(decode_box(encode_box(pk3)), pk3)

    def test_decode_known_growth_vector(self):
        # PID=0 chooses GAEM. XOR key=1 flips each 32-bit word's lowest byte.
        pk3 = pokemon(pid=0, ot=1)
        wire = encode_box(pk3)
        self.assertEqual(wire[32:36], b"\x18\x00\x00\x00")
        self.assertEqual(wire[40:44], bytes([pk3[40]^1])+pk3[41:44])

    def test_section_checksum_uses_32bit_wrap(self):
        self.assertEqual(section_checksum(b"\xff"*8), 0xFFFD)

    def test_rotation_and_counter_wrap(self):
        for rotation in range(14):
            for counter in (0, 1, 0xFFFFFFFF):
                parsed = Save(save(rotation=rotation, counter=counter))
                self.assertEqual(parsed.slot.physical, 0)
                self.assertEqual(parsed.pokemon(0).species, 25)

    def test_replace_crosses_sector_boundary_and_preserves_other_bytes(self):
        # Box slot 49 straddles storage sections 5 and 6.
        original = save(index=49)
        parsed = Save(original)
        offered = parsed.pokemon(49).pk3
        received = pokemon(133, pid=98765, nickname="EEVEE")
        result = parsed.replace(49, offered, received)
        updated = Save(result)
        self.assertEqual(updated.slot.physical, 1)
        self.assertEqual(updated.slot.counter, parsed.slot.counter+1)
        self.assertEqual(updated.pokemon(49).species, 133)
        self.assertEqual(updated.pokemon(49).pk3[41], 70)
        self.assertEqual(result[:14*4096], original[:14*4096])
        self.assertEqual(result[28*4096:], original[28*4096:])
        self.assertEqual(updated.storage[:4+49*80], parsed.storage[:4+49*80])
        self.assertEqual(updated.storage[4+50*80:], parsed.storage[4+50*80:])
        self.assertEqual(u32(updated.large, 0x1200+84)^u32(updated.small, 0xF20), 1)
        for block, offset in ((updated.small,0x28),(updated.small,0x5C),
                              (updated.large,0x5F8),(updated.large,0x3A18)):
            self.assertTrue(block[offset+132//8] & (1<<(132%8)))

    def test_receipt_export_identity_survives(self):
        parsed=Save(save())
        incoming=pokemon(133,pid=17,ot=7654321,nickname="BUDDY")
        result=Save(parsed.replace(0,parsed.pokemon(0).pk3,incoming)).pokemon(0).pk3
        # Only friendship and its checksum should differ for a non-evolving mon.
        expected=bytearray(incoming); expected[41]=70
        struct.pack_into("<H",expected,28,pokemon_checksum(expected))
        self.assertEqual(result,expected)

    def test_corrupt_newest_falls_back_without_mixing_sections(self):
        original=bytearray(save())
        original[100]^=1
        parsed=Save(bytes(original))
        self.assertEqual(parsed.slot.physical,1)
        self.assertTrue(parsed.warning)

    def test_rejects_both_corrupt_slots(self):
        original=bytearray(save()); original[100]^=1; original[14*4096+100]^=1
        with self.assertRaises(SaveError): Save(bytes(original))

    def test_rejects_truncation_rom_states_and_other_game_marker(self):
        for data in (bytes(0x10000), bytes(0x20000), b"state"):
            with self.assertRaises(SaveError): Save(data)
        original=bytearray(save())
        for slot in (0,1):
            for n in range(14):
                at=(slot*14+n)*4096
                if struct.unpack_from("<H",original,at+0xFF4)[0]==0:
                    struct.pack_into("<I",original,at+0xAC,0)
                    struct.pack_into("<H",original,at+0xFF6,section_checksum(original[at:at+SIZES[0]]))
        with self.assertRaises(SaveError): Save(bytes(original))

    def test_rejects_changed_selection_bad_checksum_mail_egg(self):
        parsed=Save(save())
        with self.assertRaises(SaveError): parsed.replace(0,pokemon(pid=99),pokemon(133))
        invalid=bytearray(pokemon()); invalid[44]^=1
        with self.assertRaises(SaveError): Pokemon(bytes(invalid))
        for mon in (pokemon(item=121),pokemon(egg=True)):
            with self.assertRaises(SaveError): Pokemon(mon).check_tradeable()

    def test_national_dex_and_trade_evolution_gate(self):
        parsed=Save(save(national=False))
        for incoming in (pokemon(152),pokemon(64)):
            with self.assertRaises(SaveError): parsed.replace(0,parsed.pokemon(0).pk3,incoming)

    def test_all_420_storage_slots_roundtrip(self):
        for i in range(420):
            parsed=Save(save(index=i))
            updated=Save(parsed.replace(i,parsed.pokemon(i).pk3,pokemon(133)))
            self.assertEqual(updated.pokemon(i).species,133)


if __name__ == "__main__": unittest.main()
