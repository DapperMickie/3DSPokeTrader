# PokeTrader

PokeTrader exchanges boxed Pokemon between FireRed or LeafGreen saves on
homebrew-enabled Nintendo 3DS systems and FireRed or LeafGreen running on
unmodified Nintendo Switch systems.

The 3DS app lets you choose a save, browse its PC boxes, and select a Pokemon. A companion program on a Linux PC handles the trade with the Switch, updates the original save, and keeps recovery files in case the process is interrupted.

![PokeTrader app overview](docs/screenshots/overview.png)

## Downloads

Get the current 3DS app and Linux bridge from the [latest GitHub release](https://github.com/DapperMickie/3DSPokeTrader/releases/latest). Releases include a HOME Menu CIA, a Homebrew Launcher build, an SD-card-ready archive, and the bridge source.

## Modes

- **Local 3DS to Switch.** A 3DS and Switch near one Linux bridge. This remains
  the default and does not use a relay. Follow the
  [local bridge guide](docs/how-to-run.md).
- **Remote 3DS to Switch.** Each player runs a bridge and both connect through a
  private relay. Follow the
  [remote 3DS-to-Switch guide](docs/remote-trading.md#configure-the-bridges).
- **Remote Switch to Switch.** Each Switch uses its own radio bridge. A first
  trade-room visit captures both offers and a second visit completes the trade.
  Follow the [two-Switch guide](docs/remote-trading.md#run-a-two-switch-trade).
- **Remote 3DS to 3DS.** Both players select boxed Pokemon in the 3DS app and
  exchange replacement saves in one session. Follow the
  [two-3DS guide](docs/remote-trading.md#run-a-two-3ds-trade).

The three remote modes are experimental and require two bridge computers plus
a self-hosted relay. Room roles keep all three pairings separate.

## Host a relay

Remote rooms need an HTTPS relay under your control. It forwards encrypted
snapshots and stores no durable trade history. Docker Compose, an existing
reverse proxy, and Portainer setups are documented in
[Host a PokeTrader relay](docs/relay.md). Local 3DS-to-Switch trading never uses
the relay.

## Current status

PokeTrader is still a hardware-test build. Save handling, recovery, bridge
pairing, and the remote coordinators have automated tests. A handful of local
physical 3DS-to-Switch trades have completed, but the three remote modes still
need end-to-end physical validation across separate systems.

It supports standard FireRed and LeafGreen saves. ROM hacks, save states, other Pokemon generations, eggs, held mail, and selecting Pokemon directly from the party are not supported.

## License

PokeTrader is licensed under AGPL-3.0-or-later. It does not include games, ROMs, Switch keys, or personal save data. Pokemon sprites remain copyright The Pokemon Company.
