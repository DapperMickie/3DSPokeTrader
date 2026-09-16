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

The Portainer deployment in `deploy/relay/portainer-compose.yml` builds from this repository and joins the existing `robsengamingproxy` network as `pokerelay:8780`. It generates a 64-character relay credential in its persistent `relay_data` volume on first startup. Read that credential once from the container, store it on both bridges, and keep it private. The process starts as root solely to initialize and write that Docker-managed volume; its root filesystem is read-only, all Linux capabilities are dropped, and privilege escalation is disabled.

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

Keep both config files and both data directories. They contain the pinned bridge identities and recovery records. Each relay room has exactly one source slot and one Switch slot. A different identity cannot replace either occupant while the room is active. After both bridges record successful completion, they clear only the finished exchange state and reuse the same room for the next trade. Do not replace a pending exchange's config or delete its recovery records. No account registration or browser control page is required.

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
  --experimental-remote
```

Use the Python interpreter with the required upstream dependencies, or pass `--python /path/to/venv/bin/python` as for local trading. If radio access requires root, use the same local privilege setup as the existing bridge.

1. Run the rebuilt 3DS app from this branch. Select the source save and Pokemon as usual, then start the exchange.
2. The bridges recognize the one pinned peer in each room and establish their encrypted channel automatically.
3. The Switch player leads the normal Direct Corner trade, accepts `3DSLINK`, sits on the left and selects a Pokemon.
4. The source bridge validates the selected Switch Pokemon against the source save. Both bridges automatically accept the current validated offer revision.
5. When the Switch-side process finishes with the matching receipt, the bridges automatically release and apply the replacement 3DS save.

X on the 3DS requests cancellation or recovery. Before commitment, the Switch engine declines the proposed exchange. After commitment may have started, the exchange remains pending for recovery; cancellation does not roll back a console save. B returns home without cancelling.

## Recover an interruption

Restart each command with its original config and data directory, then resume the pending trade on the 3DS. Bridges automatically exchange retained status again. A matching receipt from a completed Switch process releases the result automatically. A missing or mismatched record leaves the exchange uncertain; it does not produce a replacement save or retry the radio operation.

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
- Switch cancellation and reselection; each changed offer must be revalidated before automatic acceptance.
- Internet loss before acceptance, immediately after commitment and after the Switch process completes.
- Restart of each bridge and the relay at those boundaries; verify only one radio operation occurred.
- Source-save change before result application, invalid receipts and unsupported Pokemon.

The live process retains the existing 15-minute timeout. A timeout can leave an uncertain exchange and is not evidence that no trade occurred. This mode assumes cooperative friends and does not prevent save-backup duplication or promise atomic saving across consoles.

Software validation on 16 September 2026 covers encrypted trusted-room exchange, identity pinning, automatic acceptance, recovery, native save/HTTP behavior, CIA and 3DSX builds, and Compose configuration. No physical remote trade across separate networks has completed validation yet.
