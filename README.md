# PokeTrader

A homebrew 3DS app and Linux bridge for exchanging boxed Pokemon from a FireRed/LeafGreen save with an unmodified Switch running FireRed/LeafGreen.

**Version 0.2.2 is a hardware-test build.** Save handling, recovery, and the bridge API have automated tests. No physical 3DS-to-Switch trade has been performed with this app yet. The live transport reuses the pinned [frlg-ldn-trade](https://github.com/tornadus/frlg-ldn-trade) project.

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

Windows can run inspection, demo mode, and tests. Live trading needs Linux with direct access to supported Wi-Fi hardware. An ordinary WSL network connection is insufficient for LDN. We have validated USB passthrough, the RTL8192EU driver, passive reception and LDN monitor setup in WSL 2 using a custom kernel. End-to-end Switch trading through WSL is still untested. See [the WSL setup notes](docs/wsl-setup.md).

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

The prebuilt SD-card archive is `dist/PokeTrader-3ds-v0.2.2.zip`. Extract its `3ds` folder to the SD-card root, then add your generated `bridge.cfg` as described above. The separate source archive includes the Linux bridge and setup script.

Build with [devkitPro's 3DS toolchain](https://devkitpro.org/wiki/Getting_Started):

```sh
sudo sh scripts/install-makerom.sh /usr/local/bin
make -C 3ds
```

The installer pins and verifies Project CTR `makerom` 0.18.4, which is required for the CIA target but is not included in the devkitPro container.

Copy `3ds/PokeTrader.3dsx` and `3ds/PokeTrader.smdh` into `sdmc:/3ds/PokeTrader/` to launch it from Homebrew Launcher, or copy `3ds/PokeTrader.cia` to the SD card and install it with FBI to place PokeTrader on the HOME Menu.

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

This project is AGPL-3.0-or-later. No ROMs, Switch keys, or personal saves are bundled. Sprite images remain copyright The Pokemon Company; the PokeAPI distribution notice and VT323 font license are included in `3ds/assets/`. Protocol and save-format references, pinned revisions, and the upstream adapter fixes are recorded in [docs/implementation.md](docs/implementation.md).

## Graphical UI and previews

Version 0.2 uses a dual-screen graphical interface with embedded FRLG sprites and VT323 pixel text. Update the PC bridge together with the 3DS app; the box metadata endpoint requires version 0.2.

- Home: choose Trade or Settings. Pending exchanges appear as Resume trade.
- Settings: edit PC address, port and pairing token with the system keyboard, then choose Test & save. B returns home; untested edits are discarded.
- Save browser: D-pad selects a file or folder, A opens it, B goes up. Touch a row to select, then touch Open selection.
- Boxes: D-pad or touch selects a slot in the 6 by 5 grid. L/R changes boxes. A or Select Pokemon continues to trade preparation.
- Trade: start and Switch-save confirmation remain separate actions. B returns home with the recovery record retained. START exits the app.
- Messages: up/down scrolls long text; A/B continues.

[View the six-screen preview](docs/screenshots/overview.png). These are offscreen captures from the actual C renderer using example data, not captures from console hardware. Both screen sizes match the device: 400 by 240 and 320 by 240. Physical readability, touch accuracy and performance still need device testing.

To reproduce captures, compile `tests/ui_preview.c` with `3ds/source/ui.c` and `-I3ds/include`, run it from the repository root, then run `python scripts/render-ui-previews.py` with Pillow installed. `scripts/build-ui-assets.py` rebuilds the embedded assets from pinned upstream revisions. Assets are already included for normal builds.

The classic theme uses blue striped panels, cream dialogue frames, a green PC-box wallpaper and a red selection cursor. The typography is VT323, an openly licensed pixel font; it is not an extracted Pokemon game font.

## Connect from the 3DS settings

1. Connect the 3DS to your home Wi-Fi using **System Settings > Internet Settings**. Keep the Linux bridge PC on that same LAN, through Ethernet or a separate Wi-Fi adapter from the one used for Switch trading.
2. On the PC, run the installation and `pair` commands above. The generated `bridge.cfg` contains the PC IPv4 address, port, and pairing token, one per line.
3. Either copy `bridge.cfg` to `sdmc:/3ds/PokeTrader/` before launching, or open **Home > Settings** on the 3DS and enter those three values. The default port is **8765**. The token is 32 hexadecimal characters. This is the bridge token, not your Wi-Fi password or Switch keys.
4. Start the PC bridge with the `serve` command above. On the 3DS choose **Test & save**. A successful authenticated response saves the configuration to the SD card and reports **LIVE** or **DEMO**. Failed tests do not activate edited settings.
5. Return Home and choose **Trade**. A successful connection test checks the PC API only; a live Switch trade also needs the dedicated adapter, keys and upstream setup described above.

If the test fails, check the PC address and token, whether the bridge is running, and whether the PC firewall allows TCP port 8765 from your LAN. Guest-network client isolation can prevent the devices from reaching each other. No router port forwarding is needed.

During a pending trade, connection fields are locked to keep recovery on the original bridge. Test and setup help remain available. Home and settings also open without a config file. Config edits, the system keyboard, and Wi-Fi behavior still need physical 3DS validation.

[Home and settings screenshots](docs/screenshots/settings-overview.png) use sample data from the same C renderer as the app. The connected screenshot illustrates the success state; it is not evidence of a hardware connection.
