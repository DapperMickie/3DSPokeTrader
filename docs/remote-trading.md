# Experimental remote 3DS and Switch trading

Local trading is unchanged and remains the default. Remote trading is an optional mode for two cooperative friends using separate bridges and a relay they host themselves. Switch to Switch is not implemented.

This implementation has software tests but has not passed physical-console remote trade validation. Use disposable save copies for hardware testing. Both bridge commands require an explicit experimental opt-in. An internet disconnect never automatically repeats a radio trade.

## Host a relay

Use a server with a public DNS name and reachable TCP ports 80 and 443. Install Docker Engine and Compose. From the repository root:

```sh
mkdir -p deploy/relay/secrets
python3 -c 'import secrets; from pathlib import Path; Path("deploy/relay/secrets/relay-credential").write_text(secrets.token_hex(32))'
printf 'RELAY_HOST=relay.example.com\n' > deploy/relay/.env
docker compose -f deploy/relay/compose.yml --env-file deploy/relay/.env up -d --build
```

Replace `relay.example.com` with your DNS name and point its DNS record at the server. Caddy terminates HTTPS. The relay port is internal to the Compose network; do not expose either bridge's local HTTP interface to the internet. Share the relay credential privately with your friend, separately from room codes. The Docker secret file must be readable inside the unprivileged relay container.

The relay forwards encrypted snapshots and stores no durable trade records. It limits room count, message size and concurrent requests. Idle relay entries expire after ten minutes; bridge recovery records do not expire. Restarting the relay is safe because bridges resend their current snapshots. The operator can see connection metadata and room identifiers, but not the encrypted Pokemon and trainer payloads.

For an existing HTTPS reverse proxy, run `poke-trader relay --credential-file relay-credential` on loopback port 8780 and proxy `/v1/exchange` to it. Relay redirects are rejected by clients. The bridges verify the relay's TLS certificate using the operating system trust store.

## Configure the bridges

Install the remote extra on both computers:

```sh
python3 -m pip install '.[remote]'
```

The 3DS bridge needs ordinary networking and the existing local `bridge.cfg`. The Switch bridge needs the existing Linux, Wi-Fi adapter, pinned upstream checkout and Switch-key setup from [the local guide](how-to-run.md). Keep a separate internet connection while its dedicated radio communicates with the Switch.

Save the owner-issued relay credential in a private file named `relay-credential` on each bridge. On the 3DS bridge:

```sh
poke-trader remote-config --relay https://relay.example.com \
  --credential-file relay-credential --role source --output source.remote.json
```

Share the printed room code with your friend. On the Switch bridge:

```sh
poke-trader remote-config --relay https://relay.example.com \
  --credential-file relay-credential --role switch --room ROOM_CODE \
  --output switch.remote.json
```

The Switch player can omit `--room` during setup and enter their friend's code in the browser's Join room form instead. The browser saves the chosen room for restart recovery. Once a pairing is verified, switching rooms is blocked until that exchange is completed or safely cancelled.

Keep both config files and both data directories. They contain the identities and recovery records for this exchange. Each room supports one exchange; the source player creates a new config, room and data directory for the next exchange. The Switch player can then join the new room in their browser; that bridge retains separate recovery records under `rooms/ROOM_CODE`. Do not replace a pending exchange's config or delete its recovery records. No account registration is required.

## Run a trade

On the 3DS bridge:

```sh
poke-trader serve --config bridge.cfg --data remote-source-data \
  --remote source.remote.json --experimental-remote
```

On the Switch bridge, replace the example address and upstream path:

```sh
poke-trader remote-switch --remote switch.remote.json --data remote-switch-data \
  --upstream /path/to/frlg-ldn-trade --keys ~/.switch/prod.keys --phy phy1 \
  --bind 192.168.1.60 --experimental-remote
```

Use the Python interpreter with the required upstream dependencies, or pass `--python /path/to/venv/bin/python` as for local trading. If radio access requires root, use the same local privilege setup as the existing bridge.

1. Open `http://192.168.1.60:8766` on a phone or computer on the Switch bridge's private network. Enter the token from `remote-switch-data/control-token`. It is a local control token, not the relay credential.
2. Run the rebuilt 3DS app from this branch. Select the source save and Pokemon as usual, then start the exchange. Older 3DS builds do not have remote approval controls.
3. Compare the verification code shown on the 3DS and browser through your existing chat. Confirm a match on both. Do not approve mismatched codes. Pairing is retained across restarts of the same room.
4. The Switch player leads the normal Direct Corner trade, accepts `3DSLINK`, sits on the left and selects a Pokemon.
5. Both players inspect the offers using the existing species/nickname summaries and sprites. Approve on the 3DS with A and in the Switch player's browser. A changed offer clears both approvals. The source bridge validates compatibility with its save before either bridge can authorize the exchange.
6. After the Switch trade finishes, the Switch player checks the received Pokemon, saves and exits the trading room, then confirms this in the browser. The 3DS retrieves and verifies its replacement save through the existing backup and application procedure.

X on the 3DS requests cancellation or recovery. The browser has the same action. Before commitment, the Switch engine declines the proposed exchange. After commitment may have started, the exchange remains pending for recovery; cancellation does not roll back a console save. B returns home without cancelling.

## Recover an interruption

Restart each command with its original config and data directory, then resume the pending trade on the 3DS. Bridges automatically exchange retained status again. A valid received record still requires the Switch player's save confirmation. A missing or mismatched record leaves the exchange uncertain; it does not produce a replacement save or retry the radio operation.

If a bridge crashes after recording that it is launching the radio process, even before the process actually starts, recovery is deliberately uncertain. Inspect both consoles. Stop any surviving upstream process before reconciliation.

Only when neither console traded, stop the Switch bridge and run:

```sh
poke-trader remote-resolve-no-trade --remote switch.remote.json \
  --data remote-switch-data --neither-side-traded
```

Restart that bridge to transmit the cancellation to the source. A receipt prevents this command from declaring no trade. If a console traded without a usable receipt, preserve all files for manual recovery; do not rerun the trade. Both peers must reconnect to finish recovery because the relay has no offline mailbox. Trade records have no automatic expiry.

## Validation and remaining hardware work

Run software checks with the remote extra installed:

```sh
python3 -m unittest discover -v
POKETRADER_TEST_UPSTREAM=/path/to/pinned/upstream python3 -m unittest tests.test_remote_gate -v
sh scripts/test-native.sh
```

The adapter tests exercise the pinned engine without using a radio. They do not prove console timing. Before treating remote mode as supported, test:

- Physical 3DS and Switch trades across separate networks, including the normal local workflow as a regression check.
- Approval waits of 30, 120 and 300 seconds, followed by approval and decline.
- Switch cancellation and reselection before approval; stale approval buttons must never authorize a replacement offer.
- Internet loss before approval, immediately after approval and after the Switch saves.
- Restart of each bridge and the relay at those boundaries; verify only one radio operation occurred.
- Source-save change before result application, invalid receipts and unsupported Pokemon.

The live process retains the existing 15-minute timeout. A timeout can leave an uncertain exchange and is not evidence that no trade occurred. This mode assumes cooperative friends and does not prevent save-backup duplication or promise atomic saving across consoles.

Software validation on 16 September 2026: 47 tests ran on Windows, with the POSIX process-shutdown test skipped there and passing in the 13-test Linux service run. Native recovery/HTTP checks, native UI rendering, the CIA and 3DSX builds, browser rendering and Compose configuration validation passed. The Python wheel includes the browser page and sprite assets. Docker container execution was not tested because the Docker daemon was unavailable. No physical remote trade or public relay deployment was performed.
