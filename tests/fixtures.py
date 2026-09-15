"""Synthetic layout fixtures. These are not playable saves or event distributions."""
import struct
from poketrader.save import SAVE_SIZE, SIZES, PAYLOAD, SIGNATURE, section_checksum, pokemon_checksum, encode_box


def pokemon(species=25, pid=123456789, ot=1122334455, item=0, nickname="PIKACHU", egg=False):
    data = bytearray(80)
    struct.pack_into("<II", data, 0, pid, ot)
    data[8:18] = bytes(0xBB+ord(c)-65 for c in nickname[:10]).ljust(10, b"\xff")
    data[18] = 2
    data[19] = 2 | (4 if egg else 0)
    data[20:27] = b"\xbb\xbc\xff\xff\xff\xff\xff"
    struct.pack_into("<HHI", data, 32, species, item, 1000)
    data[41] = 120
    struct.pack_into("<HHHH", data, 44, 33, 0, 0, 0)
    data[52] = 35
    struct.pack_into("<I", data, 72, 0x12345678 | ((1 << 30) if egg else 0))
    struct.pack_into("<H", data, 28, pokemon_checksum(data))
    return bytes(data)


def save(*, counter=8, rotation=7, index=0, offered=None, national=True):
    data = bytearray(b"\xff"*SAVE_SIZE)
    small = bytearray(SIZES[0])
    small[:8] = b"\xcc\xbf\xbe\xff\xff\xff\xff\xff"  # RED
    struct.pack_into("<I", small, 10, 0x12345678)
    struct.pack_into("<I", small, 0xAC, 1)
    small[0x1B] = 0xB9 if national else 0
    struct.pack_into("<I", small, 0xF20, 0x1234ABCD)
    large = bytearray(0x3D68)
    large[0x34] = 1
    large[0x38:0x38+80] = encode_box(pokemon(1, pid=888))
    # Game stats stored XOR security key, including initial zero count.
    struct.pack_into("<I", large, 0x1200+21*4, 0x1234ABCD)
    storage = bytearray(0x83D0)
    storage[4+index*80:4+(index+1)*80] = encode_box(offered or pokemon())
    chunks = [small]
    chunks += [large[i*PAYLOAD:i*PAYLOAD+SIZES[i+1]] for i in range(4)]
    chunks += [storage[i*PAYLOAD:i*PAYLOAD+SIZES[i+5]] for i in range(9)]
    for slot in (0, 1):
        for section, chunk in enumerate(chunks):
            physical = (section+rotation+slot)%14
            offset = (slot*14+physical)*4096
            data[offset:offset+len(chunk)] = chunk
            struct.pack_into("<HHII", data, offset+0xFF4, section, section_checksum(chunk), SIGNATURE,
                             (counter-slot) & 0xFFFFFFFF)
    return bytes(data)
