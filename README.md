# PokeTrader

A homebrew 3DS app and Linux bridge for exchanging boxed Pokemon from a FireRed/LeafGreen save with an unmodified Switch running FireRed/LeafGreen.

**Version 0.1 is a hardware-test build.** Save handling, recovery, and the bridge API have automated tests. No physical 3DS-to-Switch trade has been performed with this app yet. The live transport reuses the pinned [frlg-ldn-trade](https://github.com/tornadus/frlg-ldn-trade) project.

## What it does

- Browse the 3DS SD card for a standard 128 KiB save, regardless of its filename extension.
- Validate FRLG section signatures, checksums, save counters, and layout.
- Browse all 14 boxes and select one Pokemon.
- Run one trade through a Linux PC with a compatible Wi-Fi adapter.
- Keep a received Pokemon file, a transaction record, and backups on the PC.
- Confirm the Switch has finished saving before replacing the source save on the SD card.
- Recover a lost acknowledgement or an interrupted file rename without starting another trade.

The 3DS is the interface and save-file client. The PC parses the save and talks to the Switch. The app does not connect directly to Pokemon HOME.

## Requirements

- A homebrew-enabled 3DS with Homebrew Launcher access and a Wi-Fi connection to the PC's LAN.
- A raw GBA FireRed/LeafGreen battery save, exactly 131,072 bytes, with the starter obtained.
- An unmodified Switch or Switch 2 running FRLG, with the Direct Corner available.
- Native Linux, Python 3.12 or newer, Git, and a supported Wi-Fi adapter for the bridge.
- Your own Switch `prod.keys`, as required by the upstream transport. Keys and games are not included.

The upstream README lists ALFA AWUS036ACHM and Realtek RTL8821CE as tested adapters. **Use a separate network connection for the 3DS-to-PC link.** The adapter used for Switch LDN must be unmanaged by NetworkManager. Keep the PC reachable through Ethernet or a second Wi-Fi adapter. Do not stop NetworkManager globally if it provides the connection your 3DS is using.

Windows can run inspection, demo mode, and tests. Live trading needs Linux with direct access to supported Wi-Fi hardware. An ordinary WSL network connection is insufficient for LDN.

## Install the bridge

From this checkout on Linux:

```sh
sh scripts/setup-bridge.sh
.venv/bin/python -m poketrader pair --host 192.168.1.50
```

Replace `192.168.1.50` with the PC's actual LAN IPv4 address. The pair command writes `bridge.cfg`. Keep this file on the PC and copy it to:

```text
sdmc:/3ds/PokeTrader/bridge.cfg
```

The config contains three lines: PC address, port, and a generated pairing token. Do not share it publicly. The bridge uses authenticated HTTP on your private LAN, without TLS. Do not expose port 8765 to the Internet.

Find the dedicated adapter with `iw dev`. For example, if its interface is `wlan1` and its phy is `phy1`:

```sh
sudo nmcli device set wlan1 managed no
sudo .venv/bin/python -m poketrader serve \
  --config bridge.cfg \
  --upstream .deps/frlg-ldn-trade \
  --keys /absolute/path/to/prod.keys \
  --phy phy1
```

The adapter names are examples; use the ones reported by your machine. The current upstream code expects root for low-level networking. The setup script itself does not change network settings. After shutting down the bridge, return that interface to NetworkManager if needed:

```sh
sudo nmcli device set wlan1 managed yes
```

## Install the 3DS app

The prebuilt SD-card archive is `dist/PokeTrader-3ds-v0.1.0.zip`. Extract its `3ds` folder to the SD-card root, then add your generated `bridge.cfg` as described above. The separate source archive includes the Linux bridge and setup script.

Build with [devkitPro's 3DS toolchain](https://devkitpro.org/wiki/Getting_Started):

```sh
make -C 3ds
```

Copy `3ds/PokeTrader.3dsx` and `3ds/PokeTrader.smdh` into `sdmc:/3ds/PokeTrader/`. Launch PokeTrader from the Homebrew Launcher. This version is a `.3dsx` application, not a CIA installer.

The repository also includes `Dockerfile.build` and a GitHub Actions build workflow. Both pin the devkitPro image used for compilation.

## First trade

1. Save normally in FRLG and close the game. Place the Pokemon you want to send in a PC box. Keep another non-egg Pokemon without mail in your party.
2. Start the Linux bridge and launch PokeTrader on the 3DS.
3. Pick the source save. Confirm its trainer name, browse boxes with L/R, and select a Pokemon.
4. On the Switch, lead a Direct Corner trade. Start the trade from the 3DS app, accept the partner named **3DSLINK**, and sit in the left chair.
5. On Switch, offer a non-evolving Pokemon without mail or an Egg. Before your source save has the National Pokedex, use a Kanto Pokemon as the return trade.
6. Finish the Switch trade, save, and leave the trading room. The upstream process can remain active while waiting for you to leave.
7. Check the received Pokemon on the Switch. Confirm completion in the 3DS app. It downloads and verifies the updated source save, preserves the previous file, and installs the result.
8. Resume from the game's battery save. If you used a VC export, import the updated save back into that title first.

The app creates an SD backup before starting the trade. Do not run the source game or edit its save while a trade is pending. If the source changes, the app refuses to overwrite it.

### Emulator saves

Select the emulator's raw battery save, often `.sav` or `.srm`. Save states are not supported. Loading an older state after trading can restore old save data, so resume through the game's normal Continue screen.

### GBA Virtual Console injections

Export the title's GBA save to an ordinary SD file using your existing save-management workflow, then select that file in PokeTrader. After the trade, import the updated file back into the **same title**. The app does not yet browse protected VC save storage or perform the export/import itself.

## Current limits

- Standard FRLG saves only. Other generations, ROM hacks, save states, containers, and 64 KiB saves are rejected.
- The save identifies the FRLG family; it does not reliably distinguish FireRed from LeafGreen. Both use the same layout. The bridge advertises itself as LeafGreen.
- Box selection only. Move party Pokemon into a box before selecting them.
- Eggs and held mail are not supported.
- On the source side, automatic import of a Pokemon that would evolve by trade is blocked. Choose a non-evolving return Pokemon on Switch. An unexpected receipt is retained for manual recovery. The real Switch handles evolution of the Pokemon it receives.
- Species names display in English. Unmapped trainer/nickname characters display as `?`; their original bytes remain intact.
- This is a save-based exchange. It updates the received record's friendship, the source Pokedex flags, and the trade statistic, but does not recreate a 3DS-side in-game animation or all save-level link metadata such as gift-ribbon descriptions.
- Successful local trading is not a guarantee of HOME acceptance or a replacement for official transfer history.

## Recovery

The 3DS keeps `sdmc:/3ds/PokeTrader/pending.txt` until the new save is written and acknowledged. On restart, it resumes that transaction. It never automatically starts another radio trade. Do not delete this file just to retry a trade.

The PC stores each transaction under `bridge-data/trades/<id>/`:

| File | Purpose |
| --- | --- |
| `original.sav` | Source save before the exchange |
| `offered.pk3` | Selected Pokemon, decrypted canonical format |
| `companion.pk3` | Non-offered party member |
| `received.pk3` | Received Pokemon, written durably at upstream commit |
| `state.json` | Persistent status and result hash |
| `result.sav` | Confirmed replacement save |
| `trade.log` | Upstream diagnostics |

If a process or connection fails without a valid receipt, the bridge marks the transaction **uncertain** and blocks other trades. Check the Switch and retained files. A successful exit code alone is never treated as proof of receipt.

Only if you have checked both sides and are certain **neither side traded**, stop the bridge and run:

```sh
.venv/bin/python -m poketrader resolve-no-trade TRANSACTION_ID --neither-side-traded
```

Then restart the bridge and the 3DS app. Never use this command to retry an exchange the Switch completed. If the Switch completed but no usable receipt exists, preserve the files and recover manually; the app cannot reconstruct information it never received.

For `import_blocked`, the received PK3 is kept unchanged. Resolve its unsupported case with a save editor and retain the transaction for reference. There is no automatic unlock for this state.

## Development and verification

```sh
python -m unittest discover -v
sh scripts/test-native.sh
python -m poketrader inspect /path/to/save.sav --box 1
```

Python tests use synthetic data and cover checksums, shuffled encryption, counter rollover, all box positions, recovery, idempotency, and the HTTP workflow. Native C tests cover SHA-256 vectors, the actual client's file-replacement recovery, and partial HTTP responses. Hardware validation is tracked in [docs/hardware-validation.md](docs/hardware-validation.md).

After installing the upstream dependencies, check the adapter without using the radio:

```sh
.venv/bin/python scripts/check-upstream.py .deps/frlg-ldn-trade
```

To rehearse the UI without radio traffic, provide an 80-byte decrypted PK3:

```sh
.venv/bin/python -m poketrader serve --config bridge.cfg --demo-receive /path/to/test.pk3
```

Demo mode is labelled **DEMO - NO SWITCH TRADE** on the client. It still writes a replacement source save when you confirm, so use a disposable copy.

## Sources and license

This project is AGPL-3.0-or-later. No ROMs, Switch keys, sprites, or personal saves are bundled. Protocol and save-format references, pinned revisions, and the upstream adapter fixes are recorded in [docs/implementation.md](docs/implementation.md).
