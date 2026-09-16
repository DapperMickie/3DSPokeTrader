# How to run PokeTrader

PokeTrader has two parts: the app on your 3DS and the bridge on a Linux PC. The 3DS and PC communicate over your local network. The PC uses a separate compatible Wi-Fi adapter to communicate with the Switch.

## What you need

- A homebrew-enabled Nintendo 3DS connected to the same local network as the PC.
- A raw FireRed or LeafGreen battery save that is exactly 131,072 bytes. You must have obtained the starter Pokemon.
- An unmodified Switch or Switch 2 running FireRed or LeafGreen with the Direct Corner available.
- A Linux PC with Python 3.12 or newer, Git, and a compatible Wi-Fi adapter.
- Your own Switch `prod.keys`, as required by [frlg-ldn-trade](https://github.com/tornadus/frlg-ldn-trade). Keys and games are not included.

The upstream project lists the ALFA AWUS036ACHM and Realtek RTL8821CE as tested adapters. Use a separate connection, such as Ethernet or a second Wi-Fi adapter, for communication between the PC and 3DS. NetworkManager must not manage the adapter used for Switch LDN.

Live trading requires Linux and direct access to the Wi-Fi hardware. Windows can run tests, inspect saves, and use demo mode. WSL requires USB passthrough and a custom setup, and a complete Switch trade through WSL remains untested. See the [WSL setup notes](wsl-setup.md).

## Download the release

Download the assets from the [latest GitHub release](https://github.com/DapperMickie/3DSPokeTrader/releases/latest).

The release contains:

- `PokeTrader-3ds-*.zip`, ready to copy to an SD card.
- `PokeTrader.cia`, for installing the app on the 3DS HOME Menu with FBI.
- `PokeTrader.3dsx` and `PokeTrader.smdh`, for the Homebrew Launcher.
- `PokeTrader-source-*.zip`, containing the Linux bridge and source code.
- `build-info.json`, containing release checksums and build information.

## Install the 3DS app

For the Homebrew Launcher, extract the release archive's `3ds` folder to the root of the 3DS SD card. The files should end up here:

```text
sdmc:/3ds/PokeTrader/PokeTrader.3dsx
sdmc:/3ds/PokeTrader/PokeTrader.smdh
```

For a HOME Menu installation, copy `PokeTrader.cia` to the SD card and install it with FBI.

## Set up the Linux bridge

Extract the source archive or clone the repository, then run:

```sh
sh scripts/setup-bridge.sh
.venv/bin/python -m poketrader pair --host 192.168.1.50
```

Replace `192.168.1.50` with the PC's LAN IPv4 address. The pairing command creates `bridge.cfg`. Keep a copy on the PC and copy another to:

```text
sdmc:/3ds/PokeTrader/bridge.cfg
```

The file contains the PC address, port, and pairing token. Do not publish it or expose port 8765 to the internet.

Find the dedicated Wi-Fi adapter and its phy with:

```sh
iw dev
```

If the adapter is `wlan1` and its phy is `phy1`, start the bridge with:

```sh
sudo nmcli device set wlan1 managed no
sudo .venv/bin/python -m poketrader serve \
  --config bridge.cfg \
  --upstream .deps/frlg-ldn-trade \
  --keys /absolute/path/to/prod.keys \
  --phy phy1
```

Use the adapter names reported by your machine. The bridge needs root access for low-level networking. When finished, return the adapter to NetworkManager if needed:

```sh
sudo nmcli device set wlan1 managed yes
```

## Configure the app without a file

You can enter the bridge settings directly in the 3DS app instead of copying `bridge.cfg`.

1. Open **Home > Settings** in PokeTrader.
2. Enter the PC address, port, and 32-character pairing token. The default port is `8765`.
3. Start the bridge on the PC.
4. Choose **Test & save** on the 3DS.

A successful test saves the settings and reports `LIVE` or `DEMO`. If it fails, check the address and token, confirm the bridge is running, and allow TCP port 8765 through the PC firewall. Both devices must be on a network that permits devices to contact each other. Router port forwarding is not needed.

## Run a trade

1. Save normally in FireRed or LeafGreen and close the game.
2. Put the Pokemon you want to send in a PC box. Keep another non-egg Pokemon without mail in your party.
3. Start the Linux bridge, then launch PokeTrader on the 3DS.
4. Select the source save and check the trainer name.
5. Browse boxes with L and R, then select a Pokemon.
6. On the Switch, lead a Direct Corner trade. Start the trade from PokeTrader, accept the partner named `3DSLINK`, and sit in the left chair.
7. Offer a non-evolving Pokemon without mail or an Egg from the Switch. If the source save does not have the National Pokedex, offer a Kanto Pokemon.
8. Complete the Switch trade, save, and leave the trading room.
9. Check the received Pokemon on the Switch, then confirm completion in PokeTrader. The app verifies and installs the updated source save while preserving the old file.
10. Resume the source game through its normal Continue screen. If the save came from a Virtual Console injection, import the updated file back into the same title first.

Do not run the source game or edit its save while a trade is pending. PokeTrader refuses to overwrite a source save that changed after the trade began.

### Emulator saves

Choose the emulator's raw battery save, usually a `.sav` or `.srm` file. Save states are not supported. Loading an old state after a trade may restore old save data.

### GBA Virtual Console injections

Export the GBA save to a normal file on the SD card with your existing save manager. Select that file in PokeTrader, then import the updated file into the same title after the trade. PokeTrader does not access protected Virtual Console save storage itself.

## Recovery

The 3DS keeps `sdmc:/3ds/PokeTrader/pending.txt` until it installs and acknowledges the replacement save. If the app closes, reopen it and resume the pending trade. Do not delete this file to force a retry.

The PC stores transaction files under `bridge-data/trades/<id>/`, including the original save, offered and received Pokemon, result save, status, and diagnostic log.

If a connection or process fails without a valid receipt, the bridge marks the transaction as `uncertain` and blocks another trade. Check the Switch and retained files before doing anything else.

Only when you have checked both systems and are certain that neither side traded, stop the bridge and run:

```sh
.venv/bin/python -m poketrader resolve-no-trade TRANSACTION_ID --neither-side-traded
```

Never use this command if the Switch completed the trade. Preserve the transaction files for manual recovery instead.

## Demo mode

Demo mode exercises the app and bridge without Switch radio traffic. Supply an 80-byte decrypted PK3:

```sh
.venv/bin/python -m poketrader serve \
  --config bridge.cfg \
  --demo-receive /path/to/test.pk3
```

The app labels this mode `DEMO - NO SWITCH TRADE`. Confirming the demo still writes a replacement source save, so use a disposable copy.

## Build from source

Install [devkitPro's 3DS toolchain](https://devkitpro.org/wiki/Getting_Started), then run:

```sh
sudo sh scripts/install-makerom.sh /usr/local/bin
make -C 3ds
```

Build outputs appear in `3ds/`:

- `PokeTrader.3dsx`
- `PokeTrader.smdh`
- `PokeTrader.cia`

The repository also includes `Dockerfile.build` for a pinned container build.

## Test the project

```sh
python -m unittest discover -v
sh scripts/test-native.sh
python -m poketrader inspect /path/to/save.sav --box 1
```

To check the upstream adapter setup without using the radio:

```sh
.venv/bin/python scripts/check-upstream.py .deps/frlg-ldn-trade
```

Hardware validation is tracked in [hardware-validation.md](hardware-validation.md). Protocol notes, save-format references, and pinned dependencies are recorded in [implementation.md](implementation.md).

## Publish a release

Update the version in `pyproject.toml`, commit the change, and push a matching `vX.Y.Z` tag:

```sh
git tag vX.Y.Z
git push origin vX.Y.Z
```

GitHub Actions runs the tests and 3DS build, packages the files, and publishes a GitHub release with generated notes. The release includes the CIA, 3DSX, SMDH, SD-card archive, source archive, and checksum manifest.

## Current limits

- Only standard 128 KiB FireRed and LeafGreen saves are accepted.
- ROM hacks, save states, save containers, 64 KiB saves, and other Pokemon generations are rejected.
- Pokemon must be selected from a PC box.
- Eggs and held mail are not supported.
- Choose a non-evolving return Pokemon on the Switch. The source-side import blocks unexpected trade evolutions.
- Species names appear in English. Unsupported trainer or nickname characters appear as `?`, but their original bytes remain unchanged.
- This process updates save data. It does not reproduce the full link-trade animation or every piece of in-game link metadata.
- A successful local trade does not guarantee Pokemon HOME acceptance or replace official transfer history.
