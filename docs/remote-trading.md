# Experimental remote 3DS and Switch trading

Local trading is unchanged and remains the default. Remote trading is an optional mode for two cooperative friends using separate bridges and a relay they host themselves. Version 0.3.0 includes an unvalidated two-session Switch-to-Switch mode.

This implementation has software tests but has not passed physical-console remote trade validation. Use disposable save copies for hardware testing. Both bridge commands require an explicit experimental opt-in. An internet disconnect never automatically repeats a radio trade.

Rooms keep their console pairing type. The existing `source` plus `switch`
roles mean one 3DS save bridge and one physical Switch bridge. The experimental
`switch-a` plus `switch-b` roles mean two physical Switch bridges. The relay
rejects mixing those role pairs in one room. The `source-a` plus `source-b`
roles connect two 3DS save bridges directly and do not start a Switch radio
process.

## Relay prerequisite

Every remote mode requires a relay under your control. Set it up first with
[Host a PokeTrader relay](relay.md). The relay uses HTTPS, forwards encrypted
snapshots, and keeps no durable trade records.

## Configure the bridges

This 3DS-to-Switch mode requires a configured [PokeTrader relay](relay.md).

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
4. The source bridge validates the selected Switch Pokemon against the source save. The 3DS shows its species, nickname and sprite while both bridges automatically accept the current validated offer revision.
5. When the Switch confirms the trade protocol and durably writes the matching receipt, the bridges automatically release and apply the replacement 3DS save. Link-room cleanup may continue afterward; the player does not need to leave the room to prove that the Pokemon was traded.

X on the 3DS requests cancellation or recovery. Before commitment, the Switch engine declines the proposed exchange. After commitment may have started, the exchange remains pending for recovery; cancellation does not roll back a console save. B returns home without cancelling.

## Run a two-Switch trade

This mode requires a configured [PokeTrader relay](relay.md).

Each Switch needs its own Linux bridge, compatible Wi-Fi adapter, keys, and a
local FireRed or LeafGreen save used only to supply a temporary simulator
Pokemon during negotiation. The bridge reads that bootstrap save but never
edits it.

Create the room on the first bridge with role `switch-a`, then join its room
code from the second bridge with role `switch-b`:

```sh
poke-trader remote-config --relay https://relay.example.com \
  --credential-file relay-credential --role switch-a --output switch-a.remote.json

poke-trader remote-config --relay https://relay.example.com \
  --credential-file relay-credential --role switch-b --room ROOM_CODE \
  --output switch-b.remote.json
```

Run `remote-switch` on both computers with that computer's config and bootstrap
save:

```sh
poke-trader remote-switch --remote switch-a.remote.json \
  --data remote-switch-a-data --upstream /path/to/frlg-ldn-trade \
  --keys ~/.switch/prod.keys --phy phy1 --bootstrap-save /path/to/bootstrap.sav \
  --experimental-remote
```

The players enter Direct Corner twice. On the first visit, each selects the
Pokemon they want to trade. The bridges capture both exact records and decline
before commitment. After both first sessions close, each bridge starts a second
session containing the other player's selected Pokemon. Each player re-enters
Direct Corner and selects the same local Pokemon. Matching selections commit
automatically; a changed selection is declined. There is no browser or terminal
confirmation.

## Run a two-3DS trade

This mode requires a configured [PokeTrader relay](relay.md).

Create a `source-a` config on one bridge and join its room with `source-b` on
the other:

```sh
poke-trader remote-config --relay https://relay.example.com \
  --credential-file relay-credential --role source-a --output source-a.remote.json

poke-trader remote-config --relay https://relay.example.com \
  --credential-file relay-credential --role source-b --room ROOM_CODE \
  --output source-b.remote.json
```

Run the ordinary 3DS bridge server on both computers:

```sh
poke-trader serve --config bridge.cfg --data remote-source-a-data \
  --remote source-a.remote.json --experimental-remote
```

Each player uses the existing 3DS app to choose a save and boxed Pokemon. Once
both selections arrive, each bridge validates the other record against its
local save. Matching proposals release both replacement saves automatically.
This is a single-session exchange because both selected records are known
before either save is replaced. No Switch, Switch keys, dedicated radio, web
interface, or terminal confirmation is involved.

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
