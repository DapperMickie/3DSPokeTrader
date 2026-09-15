# Hardware validation

No physical console trade has been run with this application yet. Local tests do not establish wireless reliability, actual SD flush behavior, or acceptance by a particular Switch game update.

## First bench test

- Record 3DS model, homebrew environment, source game region, emulator or VC export tool, Switch game version, Linux version, adapter chipset/driver, and upstream revision.
- Start with copies of expendable standard FRLG saves and ordinary non-evolving Kanto Pokemon without mail.
- Confirm the file browser shows the expected save and the bridge shows the correct trainer and box contents.
- Complete one Switch trade using the documented Direct Corner procedure.
- Confirm the Switch saved and exited, then apply the source save.
- Load the source game normally and inspect the received Pokemon, original trainer, nickname, stats, held item, Pokedex entry and box neighbors.
- Verify the source and result through an independent save reader such as PKHeX.
- Repeat for a VC-exported save and confirm the updated file imports into the correct title.

## Recovery checks

- Disconnect 3DS Wi-Fi while the PC trade continues. Reconnect and recover the same transaction.
- Close the app after the Switch finishes, before downloading the result. Relaunch and recover.
- Interrupt acknowledgement after source application. Confirm recovery recognizes the result and does not trade again.
- Modify the source save after selection. Confirm the app refuses to overwrite it.
- Terminate the upstream process before any trade. Confirm the state becomes uncertain and the bridge blocks a new trade.
- Confirm two physical adapters or Ethernet plus the LDN adapter keep the PC reachable throughout trading.

Do not test power loss on the only copy of a save. All files under the transaction directory and all SD backups should remain available for comparison.

## Release record

Add actual hardware results here after testing. Do not mark an item complete based solely on a synthetic fixture, demo-mode exchange, compile, or upstream demonstration.
