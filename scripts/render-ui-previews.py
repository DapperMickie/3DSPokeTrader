"""Build screen panels and a complete overview from native renderer captures."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path("docs/screenshots")
background = "#e6ebe5"
ink = "#153b40"


def font(size):
    for name in ["DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


rows = [
    ("01  SETUP", [
        ("07-home", "Home"),
        ("08-settings", "Bridge settings"),
        ("09-connected", "Connection tested"),
    ]),
    ("02  CHOOSE A POKEMON", [
        ("01-save-browser", "Choose a save"),
        ("02-pokemon-box", "Browse your boxes"),
        ("03-start-trade", "Ready to trade"),
    ]),
    ("03  TRADE AND SAVE", [
        ("11-trading", "Live exchange"),
        ("04-confirm-save", "Confirm the Switch saved"),
        ("06-complete", "Save updated"),
    ]),
    ("04  RECOVERY AND COMPATIBILITY", [
        ("10-resume-home", "Resume a pending trade"),
        ("05-recovery", "Check an interrupted trade"),
        ("12-trade-fallback", "Missing sprite data / demo"),
    ]),
]

panels = {}
for _, screens in rows:
    for name, title in screens:
        panel = Image.new("RGB", (424, 538), background)
        ImageDraw.Draw(panel).text((12, 4), title, font=font(20), fill=ink)
        for which, y in [("top", 38), ("bottom", 290)]:
            with Image.open(root / f"{name}-{which}.ppm") as image:
                image.save(root / f"{name}-{which}.png")
                panel.paste(image, ((424-image.width)//2, y))
        panel.save(root / f"{name}.png")
        panels[name] = panel

overview = Image.new("RGB", (1344, 2500), background)
draw = ImageDraw.Draw(overview)
draw.text((24, 20), "POKETRADER", font=font(36), fill=ink)
draw.text((24, 67), "All 12 screens | Read left to right, then down | Top and touch screens shown together", font=font(18), fill=ink)
for row, (heading, screens) in enumerate(rows):
    y = 115 + row * 590
    draw.rectangle((24, y, 1320, y+32), fill=ink)
    draw.text((36, y+5), heading, font=font(18), fill="white")
    for column, (name, _) in enumerate(screens):
        overview.paste(panels[name], (24+column*440, y+42))
overview.save(root / "overview.png")

settings = Image.new("RGB", (896, 1116), background)
for i, name in enumerate(["07-home", "08-settings", "09-connected", "10-resume-home"]):
    settings.paste(panels[name], (16+i%2*440, 12+i//2*552))
settings.save(root / "settings-overview.png")

# Animation frames come from the same C renderer used by the 3DS app.
frames = []
for i in range(40):
    panel = Image.new("RGB", (424, 530), background)
    for which, y in [("top", 10), ("bottom", 266)]:
        with Image.open(root / f"trade-frame-{i:02d}-{which}.ppm") as image:
            panel.paste(image, ((424-image.width)//2, y))
    frames.append(panel)
frames[0].save(root / "trade-animation.gif", save_all=True,
               append_images=frames[1:], duration=80, loop=0)
