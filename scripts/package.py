"""Package only whitelisted source and build files; never include saves or keys."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parent.parent
with (ROOT/"pyproject.toml").open("rb") as project_file:
    project_version = tomllib.load(project_file)["project"]["version"]
parser = argparse.ArgumentParser()
parser.add_argument("--binaries", type=Path, default=ROOT/"3ds")
parser.add_argument("--output", type=Path, default=ROOT/"dist")
parser.add_argument("--version", default=project_version)
args = parser.parse_args()
if args.version != project_version:
    parser.error(
        f"release version {args.version!r} does not match pyproject.toml version {project_version!r}"
    )
version = args.version
out = args.output
out.mkdir(exist_ok=True)
binary_files = [args.binaries/"PokeTrader.3dsx", args.binaries/"PokeTrader.smdh", args.binaries/"PokeTrader.cia"]
assert binary_files[0].read_bytes()[:4] == b"3DSX", "Not a valid 3DSX header"
assert binary_files[1].read_bytes()[:4] == b"SMDH", "Not a valid SMDH header"
manifest = {
    "version": version,
    "built_at_utc": datetime.now(timezone.utc).isoformat(),
    "hardware_trade_tested": False,
    "toolchain": "devkitARM GCC 16.1.0",
    "toolchain_image": "devkitpro/devkitarm@sha256:15b79ce75822c289538d8153da5fa7aafe5e6adc32ad8a575a197beca0f0761b",
    "upstream_revision": "13809c21b6e992097f98453b7cbc9e2bc30bbf7c",
    "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in binary_files},
}
manifest_path = out/"build-info.json"
manifest_path.write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
sd_zip = out/f"PokeTrader-3ds-v{version}.zip"
with zipfile.ZipFile(sd_zip,"w",zipfile.ZIP_DEFLATED) as archive:
    for path in binary_files:
        archive.write(path, path.name if path.suffix == ".cia" else "3ds/PokeTrader/"+path.name)
    archive.write(ROOT/"LICENSE","LICENSE")
    for license in (ROOT/"3ds/assets").glob("*.txt"):
        archive.write(license,"licenses/"+license.name)
    archive.write(manifest_path,"build-info.json")
    archive.writestr("INSTALL.txt",
        f"PokeTrader {version} - hardware-test build\n\n"
        "Copy the 3ds folder to the root of your 3DS SD card.\n"
        "Generate bridge.cfg on the Linux PC with the pair command.\n"
        "Copy it to /3ds/PokeTrader/bridge.cfg on the SD card.\n"
        "Launch PokeTrader from Homebrew Launcher.\n\n"
        "Alternatively, install PokeTrader.cia with FBI to place it on the HOME Menu.\n\n"
        "A Linux bridge, dedicated compatible Wi-Fi adapter, and your own\n"
        "Switch keys are required for local 3DS-to-Switch trading.\n"
        "Remote bridge modes and relay setup are documented under docs/.\n"
        "See docs/how-to-run.md for the local setup.\n"
        "No physical console trade has been tested with this build.\n"
        "Use a disposable save copy for the first hardware test.\n")
source_files = [ROOT/p for p in ("README.md","LICENSE","pyproject.toml","Dockerfile.build",
                                ".gitignore",".gitattributes",".dockerignore")]
for directory in ("poketrader","3ds","scripts","tests","docs","deploy",".github"):
    for path in (ROOT/directory).rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or "build" in path.parts:
            continue
        if path.suffix in (".py",".c",".h",".json",".md",".sh",".yml",".bin",".txt",".png",".gif",".rsf",".html") or path.name in ("Makefile", "Dockerfile", "Caddyfile", "Dockerfile.dockerignore"):
            source_files.append(path)
source_zip = out/f"PokeTrader-source-v{version}.zip"
with zipfile.ZipFile(source_zip,"w",zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(set(source_files)): archive.write(path,path.relative_to(ROOT))
for path in (sd_zip,source_zip):
    with zipfile.ZipFile(path) as archive: assert archive.testzip() is None
    print(f"{path.name}: {path.stat().st_size} bytes")
