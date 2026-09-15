"""Strict 128 KiB FRLG save reader/writer and explicit PK3 encoding.

Layout references are recorded in docs/implementation.md. All offsets are
little-endian. Save sections can rotate; their physical order is never assumed.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from importlib.resources import files


class SaveError(ValueError):
    pass


SAVE_SIZE = 0x20000
SECTOR_SIZE = 0x1000
PAYLOAD = 0xF80
SIZES = (0xF24, 0xF80, 0xF80, 0xF80, 0xEE8,
         0xF80, 0xF80, 0xF80, 0xF80, 0xF80, 0xF80, 0xF80, 0xF80, 0x7D0)
SIGNATURE = 0x08012025
ORDERS = ("GAEM", "GAME", "GEAM", "GEMA", "GMAE", "GMEA",
          "AGEM", "AGME", "AEGM", "AEMG", "AMGE", "AMEG",
          "EGAM", "EGMA", "EAGM", "EAMG", "EMGA", "EMAG",
          "MGAE", "MGEA", "MAGE", "MAEG", "MEGA", "MEAG")
SPECIES = {int(k): v for k, v in json.loads(
    files("poketrader").joinpath("species.json").read_text(encoding="utf-8")).items()}
SPECIES_INFO = {int(k): v for k, v in json.loads(
    files("poketrader").joinpath("species-info.json").read_text(encoding="utf-8")).items()}
NATURES = ("Hardy", "Lonely", "Brave", "Adamant", "Naughty", "Bold", "Docile", "Relaxed",
           "Impish", "Lax", "Timid", "Hasty", "Serious", "Jolly", "Naive", "Modest", "Mild",
           "Quiet", "Bashful", "Rash", "Calm", "Gentle", "Sassy", "Careful", "Quirky")
CHARS = {0: " ", 0xAB: "!", 0xAC: "?", 0xAD: ".", 0xAE: "-",
         0xB4: "'", 0xB8: ",", 0xBA: "/"}
CHARS.update({0xA1 + n: c for n, c in enumerate("0123456789")})
CHARS.update({0xBB + n: c for n, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")})
CHARS.update({0xD5 + n: c for n, c in enumerate("abcdefghijklmnopqrstuvwxyz")})


def text(data: bytes) -> str:
    # Display only. Unknown language glyphs never alter the stored bytes.
    return "".join(CHARS.get(x, "?") for x in data.split(b"\xff", 1)[0])


def u16(data, at):
    return struct.unpack_from("<H", data, at)[0]


def u32(data, at):
    return struct.unpack_from("<I", data, at)[0]


def section_checksum(data: bytes) -> int:
    total = sum(struct.unpack(f"<{len(data) // 4}I", data)) & 0xFFFFFFFF
    return ((total >> 16) + (total & 0xFFFF)) & 0xFFFF


def pokemon_checksum(canonical: bytes) -> int:
    return sum(struct.unpack("<24H", canonical[32:80])) & 0xFFFF


def experience_at(growth: str, level: int) -> int:
    if level <= 1:
        return 0
    cube = level**3
    if growth == "MEDIUM_FAST": return cube
    if growth == "FAST": return 4*cube//5
    if growth == "SLOW": return 5*cube//4
    if growth == "MEDIUM_SLOW": return 6*cube//5 - 15*level**2 + 100*level - 140
    if growth == "ERRATIC":
        if level <= 50: return (100-level)*cube//50
        if level <= 68: return (150-level)*cube//100
        if level <= 98: return ((1911-10*level)//3)*cube//500
        return (160-level)*cube//100
    if growth == "FLUCTUATING":
        if level <= 15: return ((level+1)//3+24)*cube//50
        if level <= 36: return (level+14)*cube//50
        return (level//2+32)*cube//50
    raise SaveError("Unknown experience growth rate.")


def decode_box(encrypted: bytes) -> bytes:
    if len(encrypted) != 80:
        raise SaveError("A boxed Pokemon must contain exactly 80 bytes.")
    out = bytearray(encrypted)
    key = u32(out, 0) ^ u32(out, 4)
    plain = b"".join(struct.pack("<I", u32(out, i) ^ key) for i in range(32, 80, 4))
    order = ORDERS[u32(out, 0) % 24]
    out[32:80] = b"".join(plain[order.index(c)*12:order.index(c)*12+12] for c in "GAEM")
    return bytes(out)


def encode_box(canonical: bytes) -> bytes:
    if len(canonical) != 80:
        raise SaveError("Expected an 80-byte decrypted PK3.")
    out = bytearray(canonical)
    order = ORDERS[u32(out, 0) % 24]
    out[32:80] = b"".join(canonical[32+"GAEM".index(c)*12:44+"GAEM".index(c)*12] for c in order)
    key = u32(out, 0) ^ u32(out, 4)
    for i in range(32, 80, 4):
        struct.pack_into("<I", out, i, u32(out, i) ^ key)
    return bytes(out)


@dataclass(frozen=True)
class Pokemon:
    pk3: bytes

    def __post_init__(self):
        if len(self.pk3) != 80 or pokemon_checksum(self.pk3) != u16(self.pk3, 28):
            raise SaveError("Pokemon checksum is invalid.")
        if self.species not in SPECIES:
            raise SaveError("Empty slot or unsupported species identifier.")
        if self.pk3[19] & 1 or not self.pk3[19] & 2:
            raise SaveError("Invalid Pokemon header or Bad Egg.")

    @property
    def species(self):
        return u16(self.pk3, 32)

    @property
    def dex(self):
        return SPECIES[self.species][1]

    @property
    def name(self):
        return SPECIES[self.species][0]

    @property
    def nickname(self):
        return text(self.pk3[8:18])

    @property
    def summary(self):
        return f"{self.name} / {self.nickname}"

    @property
    def egg(self):
        return bool(u32(self.pk3, 72) & (1 << 30) or self.pk3[19] & 4)

    @property
    def item(self):
        return u16(self.pk3, 34)

    def check_tradeable(self):
        if self.egg:
            raise SaveError("Egg trades are not supported in this version.")
        if 121 <= self.item <= 132:
            raise SaveError("Remove held mail in the game before trading.")


@dataclass
class Slot:
    physical: int
    counter: int
    sectors: dict[int, int]


class Save:
    def __init__(self, data: bytes):
        if len(data) != SAVE_SIZE:
            raise SaveError("Select a raw 128 KiB FRLG battery save, not a save state or ROM. Export VC saves first.")
        self.data = bytes(data)
        valid = []
        for physical in (0, 1):
            try:
                valid.append(self._read_slot(physical))
            except SaveError:
                pass
        if not valid:
            raise SaveError("No complete FRLG save slot passed section checksums and layout checks.")
        self.slot = valid[0]
        if len(valid) == 2:
            difference = (valid[1].counter - valid[0].counter) & 0xFFFFFFFF
            if difference == 0:
                if any(self._payload(valid[0], i) != self._payload(valid[1], i) for i in range(14)):
                    raise SaveError("Save slots have equal counters but different data. Save again in the game.")
            elif difference == 0x80000000:
                raise SaveError("Ambiguous save counters. Save again in the game.")
            elif difference < 0x80000000:
                self.slot = valid[1]
        self.warning = "" if len(valid) == 2 else "Only one valid save slot; using the complete slot."
        self.small = self._payload(self.slot, 0)
        self.large = b"".join(self._payload(self.slot, i) for i in range(1, 5))
        self.storage = b"".join(self._payload(self.slot, i) for i in range(5, 14))
        self.trainer = text(self.small[:8])
        self.trainer_id = u32(self.small, 10)

    def _payload(self, slot, section):
        offset = slot.sectors[section]
        return self.data[offset:offset+SIZES[section]]

    def _read_slot(self, physical):
        sectors = {}
        counters = set()
        for n in range(14):
            offset = (physical * 14 + n) * SECTOR_SIZE
            section, checksum, signature, counter = struct.unpack_from("<HHII", self.data, offset+0xFF4)
            if section >= 14 or section in sectors or signature != SIGNATURE:
                raise SaveError("Invalid section footer.")
            if section_checksum(self.data[offset:offset+SIZES[section]]) != checksum:
                raise SaveError("Invalid section checksum.")
            sectors[section] = offset
            counters.add(counter)
        if len(counters) != 1:
            raise SaveError("Incomplete save slot with mixed counters.")
        small = self.data[sectors[0]:sectors[0]+SIZES[0]]
        # FRLG's dummy game flags at 0xAC are 1/0; RS/E have other layouts.
        if u32(small, 0xAC) != 1 or small[8] > 1 or small[16] >= 60 or small[17] >= 60:
            raise SaveError("Save is not a supported FRLG layout.")
        count = self.data[sectors[1]+0x34]
        if not 1 <= count <= 6 or self.data[sectors[5]] >= 14:
            raise SaveError("Save has no starter, or has an unsupported party/box layout.")
        return Slot(physical, counters.pop(), sectors)

    def pokemon(self, index: int) -> Pokemon:
        if not 0 <= index < 420:
            raise SaveError("Box slot is out of range.")
        offset = 4 + index * 80  # struct padding aligns BoxPokemon after currentBox.
        return Pokemon(decode_box(self.storage[offset:offset+80]))

    def companion(self) -> Pokemon:
        # A genuine party member is sent as the non-offered slot. It never leaves the save.
        for index in range(self.large[0x34]):
            offset = 0x38 + index * 100
            try:
                mon = Pokemon(decode_box(self.large[offset:offset+80]))
                mon.check_tradeable()
                return mon
            except SaveError:
                continue
        raise SaveError("Put a healthy non-egg Pokemon without mail in your party, then save again.")

    def box_lines(self, box: int) -> str:
        if not 0 <= box < 14:
            raise SaveError("Box number is out of range.")
        lines = []
        for index in range(box*30, box*30+30):
            offset = 4+index*80
            raw = self.storage[offset:offset+80]
            if raw == bytes(80):
                lines.append(f"{index}\t(empty)")
                continue
            try:
                mon = self.pokemon(index)
                suffix = " [Egg]" if mon.egg else ""
                lines.append(f"{index}\t{mon.summary}{suffix}")
            except SaveError:
                lines.append(f"{index}\t(invalid Pokemon)")
        return "\n".join(lines)+"\n"

    def box_details(self, box: int) -> str:
        """Read-only presentation metadata. Never alters the source record."""
        if not 0 <= box < 14:
            raise SaveError("Box number is out of range.")
        rows = []
        for index in range(box*30, box*30+30):
            raw = self.storage[4+index*80:4+(index+1)*80]
            # index, dex, shiny, eligible, level, kind, types, species, nickname,
            # original trainer, public TID, nature, and an eligibility explanation.
            row = [index, 0, 0, 0, 0, 0, "", "", "", "", "", 0, "", "Empty slot"]
            if raw != bytes(80):
                try:
                    mon = self.pokemon(index)
                    growth, type_a, type_b = SPECIES_INFO[mon.species]
                    exp = u32(mon.pk3, 36)
                    level = max(n for n in range(1, 101) if experience_at(growth, n) <= exp)
                    pid, ot = u32(mon.pk3, 0), u32(mon.pk3, 4)
                    shiny = ((pid >> 16) ^ (pid & 65535) ^ (ot >> 16) ^ (ot & 65535)) < 8
                    eligible, reason = 1, "Ready to trade"
                    try:
                        mon.check_tradeable()
                    except SaveError as exc:
                        eligible, reason = 0, str(exc)
                    row = [index, mon.dex, int(shiny), eligible, level, 2 if mon.egg else 1,
                           type_a, type_b, mon.name.title(), mon.nickname, text(mon.pk3[20:27]),
                           ot & 65535, NATURES[pid % 25], reason]
                except SaveError:
                    row[5], row[13] = 3, "Invalid Pokemon record"
            rows.append("\t".join(str(value).replace("\t", " ").replace("\n", " ") for value in row))
        return "\n".join(rows)+"\n"

    def replace(self, index: int, expected: bytes, received: bytes) -> bytes:
        if self.pokemon(index).pk3 != expected:
            raise SaveError("The selected Pokemon changed. Refusing to overwrite it.")
        incoming = Pokemon(received)
        incoming.check_tradeable()
        # This version preserves the received record without simulating an evolution.
        # The UI explicitly tells users to choose non-evolving return Pokemon.
        if evolution_target(incoming):
            raise SaveError("The received Pokemon evolves by trade. Its file is retained for recovery; automatic import is blocked.")
        if incoming.dex > 151 and self.small[0x1B] != 0xB9:
            raise SaveError("The source save needs the National Pokedex for this received Pokemon.")
        mon = bytearray(received)
        mon[41] = 70  # FRLG TradeMons resets friendship to 70.
        struct.pack_into("<H", mon, 28, pokemon_checksum(mon))
        storage = bytearray(self.storage)
        storage[4+index*80:4+(index+1)*80] = encode_box(bytes(mon))
        small, large = bytearray(self.small), bytearray(self.large)
        dex_index = incoming.dex-1
        for block, base in ((small, 0x28), (small, 0x5C), (large, 0x5F8), (large, 0x3A18)):
            block[base+dex_index//8] |= 1 << (dex_index % 8)
        if incoming.dex in (201, 327):
            personality_at = 0x1C if incoming.dex == 201 else 0x20
            if not self.small[0x28+dex_index//8] & (1 << (dex_index % 8)):
                small[personality_at:personality_at+4] = mon[:4]
        # Encrypted game statistic: count the completed exchange.
        stats_at = 0x1200 + 21*4
        key = u32(small, 0xF20)
        count = min((u32(large, stats_at) ^ key)+1, 0xFFFFFF)
        struct.pack_into("<I", large, stats_at, count ^ key)
        payloads = [bytes(small)]
        payloads += [bytes(large[i*PAYLOAD:i*PAYLOAD+SIZES[i+1]]) for i in range(4)]
        payloads += [bytes(storage[i*PAYLOAD:i*PAYLOAD+SIZES[i+5]]) for i in range(9)]
        out = bytearray(self.data)
        # Write a complete next-generation slot; retain the previous slot and sectors 28-31.
        destination = 1-self.slot.physical
        for section, payload in enumerate(payloads):
            source = self.slot.sectors[section]
            physical_index = source//SECTOR_SIZE % 14
            target = (destination*14+physical_index)*SECTOR_SIZE
            out[target:target+SECTOR_SIZE] = self.data[source:source+SECTOR_SIZE]
            out[target:target+len(payload)] = payload
            struct.pack_into("<HHII", out, target+0xFF4, section, section_checksum(payload),
                             SIGNATURE, (self.slot.counter+1) & 0xFFFFFFFF)
        result = bytes(out)
        checked = Save(result)
        if checked.pokemon(index).pk3 != bytes(mon):
            raise SaveError("Updated save failed read-back verification.")
        return result


def evolution_target(mon: Pokemon) -> int | None:
    if mon.item == 195:  # Everstone suppresses trade evolution in generation 3.
        return None
    simple = {64: 65, 67: 68, 75: 76, 93: 94}
    held = {(61, 187): 186, (79, 187): 199, (95, 199): 208, (123, 199): 212,
            (117, 201): 230, (137, 218): 233, (373, 192): 374, (373, 193): 375}
    return simple.get(mon.species) or held.get((mon.species, mon.item))
