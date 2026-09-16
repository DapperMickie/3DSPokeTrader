"""Bake compact, offline UI artwork and fonts. Requires Pillow, only when regenerating."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import io
import struct
import urllib.request
import time

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT/".tools/ui-assets"
OUT = ROOT/"3ds/romfs/ui"
SPRITES = "2ecb4eeacd5a1718621fc30f12772e3f60d830b9"
FONTS = "809e4d8b8d7e9364a914909bb777679606c178b8"
CACHE.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)


def fetch(url, name):
    path = CACHE/name
    if not path.exists():
        for attempt in range(4):
            try:
                data = urllib.request.urlopen(url, timeout=40).read()
                path.write_bytes(data)
                break
            except Exception:
                if attempt == 3: raise
                time.sleep(attempt+1)
    return path.read_bytes()


def sprite(entry):
    dex, shiny = entry
    variant = "shiny/" if shiny else ""
    url = f"https://raw.githubusercontent.com/PokeAPI/sprites/{SPRITES}/sprites/pokemon/versions/generation-iii/firered-leafgreen/{variant}{dex}.png"
    image = Image.open(io.BytesIO(fetch(url, f"{dex}-{'shiny' if shiny else 'normal'}.png"))).convert("RGBA")
    assert image.size == (64, 64), (dex, image.size)
    pixels = [0 if a < 128 else 0x8000 | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
              for r, g, b, a in image.getdata()]
    runs = bytearray()
    at = 0
    while at < len(pixels):
        stop = at+1
        while stop < len(pixels) and pixels[stop] == pixels[at] and stop-at < 255:
            stop += 1
        runs += struct.pack("<BH", stop-at, pixels[at])
        at = stop
    return runs


entries = [(dex, shiny) for shiny in (False, True) for dex in range(1, 387)]
with ThreadPoolExecutor(max_workers=12) as pool:
    art = list(pool.map(sprite, entries))
header = bytearray(b"PTART01\0") + struct.pack("<I", len(art))
offset = 12 + 8*len(art)
for item in art:
    header += struct.pack("<II", offset, len(item))
    offset += len(item)
(OUT/"art.bin").write_bytes(header + b"".join(art))
(ROOT/"poketrader/art.bin").write_bytes(header + b"".join(art))
print("Baked 386 normal and 386 shiny FRLG portraits.", flush=True)

url = f"https://raw.githubusercontent.com/google/fonts/{FONTS}/ofl/vt323/VT323-Regular.ttf"
font_bytes = fetch(url, "VT323.ttf")
font_data = bytearray(b"PTFONT1\0") + struct.pack("<I", 4)
for size in (20, 20, 24, 28):
    font = ImageFont.truetype(io.BytesIO(font_bytes), size=size)
    ascent, descent = font.getmetrics()
    font_data += struct.pack("<BB", ascent, ascent+descent)
    for code in range(32, 127):
        char = chr(code)
        x0, y0, x1, y1 = font.getbbox(char, anchor="ls")
        width, height = x1-x0, y1-y0
        advance = round(font.getlength(char))
        glyph = Image.new("L", (max(1, width), max(1, height)))
        ImageDraw.Draw(glyph).text((-x0, -y0), char, font=font, fill=255, anchor="ls")
        font_data += struct.pack("<BBBbb", advance, width, height, x0, y0)
        if width and height: font_data += glyph.point(lambda value: 255 if value >= 128 else 0).tobytes()
(OUT/"font.bin").write_bytes(font_data)
license_dir = ROOT/"3ds/assets"
license_dir.mkdir(exist_ok=True)
(license_dir/"VT323-OFL.txt").write_bytes(fetch(
    f"https://raw.githubusercontent.com/google/fonts/{FONTS}/ofl/vt323/OFL.txt", "VT323-OFL.txt"))
(license_dir/"PokeAPI-sprites-LICENCE.txt").write_bytes(fetch(
    f"https://raw.githubusercontent.com/PokeAPI/sprites/{SPRITES}/LICENCE.txt", "sprites-LICENCE.txt"))
print("Baked monochrome VT323 font sizes 20, 20, 24 and 28 with source licenses.", flush=True)
