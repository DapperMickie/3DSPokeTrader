# Implementation notes

## Components

`3ds/source/main.c` implements a graphical 3DS interface with a file picker, 14-box browser, trade status, and recovery. `http.c`, `hash.c`, and `files.c` compile both for ARM11 and native Linux, so their networking and file-write code can be tested outside the console.

`poketrader/save.py` reads and writes saves. The bridge owns this parsing code; the 3DS uploads a copy and only installs a complete, hash-verified result. `service.py` owns transaction state; `server.py` exposes the authenticated LAN protocol. `backend.py` launches one pinned upstream trade process. `upstream_runner.py` adapts its persistence and Pokemon input format without altering its radio state machine.

## Save handling

References checked against [pret/pokefirered](https://github.com/pret/pokefirered/tree/c75f352304d529f6ba92d4f74b9cf8b5c3810788):

- [`src/save.c`](https://github.com/pret/pokefirered/blob/c75f352304d529f6ba92d4f74b9cf8b5c3810788/src/save.c) and [`include/save.h`](https://github.com/pret/pokefirered/blob/c75f352304d529f6ba92d4f74b9cf8b5c3810788/include/save.h): 32 sectors, rotating section IDs, two save slots, additive checksums, and signature `0x08012025`.
- [`include/global.h`](https://github.com/pret/pokefirered/blob/c75f352304d529f6ba92d4f74b9cf8b5c3810788/include/global.h): SaveBlock2 size `0xF24`, SaveBlock1 size `0x3D68`, trainer fields, party offsets, Pokedex flags and encryption key.
- [`include/pokemon_storage_system.h`](https://github.com/pret/pokefirered/blob/c75f352304d529f6ba92d4f74b9cf8b5c3810788/include/pokemon_storage_system.h): storage size `0x83D0`. The boxed array begins at byte 4 after C struct alignment, despite the member's `0x0001` source comment.
- [`src/trade_scene.c`](https://github.com/pret/pokefirered/blob/c75f352304d529f6ba92d4f74b9cf8b5c3810788/src/trade_scene.c): normal trade friendship 70, seen/caught flags, and game statistic increment.
- [`include/constants/species.h`](https://github.com/pret/pokefirered/blob/c75f352304d529f6ba92d4f74b9cf8b5c3810788/include/constants/species.h) and [`include/constants/pokedex.h`](https://github.com/pret/pokefirered/blob/c75f352304d529f6ba92d4f74b9cf8b5c3810788/include/constants/pokedex.h): factual internal species IDs, names and National Dex numbers used in `species.json`. Internal Hoenn IDs are not National Dex numbers.

Each slot must have all 14 distinct sections, valid checksums, and one counter. The reader chooses the newest complete slot using 32-bit wrap-aware comparison; it never combines sections from different slots. One invalid slot produces a warning and uses the other. Ambiguous counters or inconsistent same-counter data are rejected.

Writing builds the next complete slot in the inactive half, retaining the prior active slot and the Hall of Fame/Trainer Tower sectors. It re-parses the result before making it available. Boxed Pokemon crossing section boundaries are handled through a reconstructed storage buffer.

Raw save Pokemon are encrypted/shuffled, while exported `.pk3` files are decrypted and ordered Growth/Attacks/EVs/Misc. The code always chooses the conversion explicitly; it does not infer it from filename or checksum. The header, original trainer, personality, nickname bytes and ribbons remain unchanged by encoding.

FRLG's layout checks identify the family, not an exact release, region, revision, or ROM-hack identity. They cannot prove a save is unmodified. Version 0.1 targets standard layouts and has only synthetic local validation.

## Upstream integration

The bridge pins [tornadus/frlg-ldn-trade at 13809c21b6e992097f98453b7cbc9e2bc30bbf7c](https://github.com/tornadus/frlg-ldn-trade/tree/13809c21b6e992097f98453b7cbc9e2bc30bbf7c). Its AGPL-3.0 source is fetched by the setup script and not copied into this repository.

Two wrapper adaptations are needed:

1. `run_live()` calls `save_received(engine, args, lg)` at commit, but that revision's `args` is local to `main()`. The wrapper supplies the expected configuration and replaces the persistence callback with checksum validation, an fsynced temporary file, atomic rename, and parent-directory fsync on Linux.
2. Its general input loader guesses encrypted versus decrypted bytes. The wrapper knows our inputs are canonical PK3, encrypts them explicitly, and uses the upstream stat builder for the 20-byte party tail. This avoids ambiguous checksum-based format guesses, including zero XOR keys.

In local mode, the wrapper does not change packet parsing, session discovery, the offered-slot protocol, timing, or the trade state machine. It offers party slot 1 and uses a real party member from the source save in non-offered slot 0. The companion is not removed from the save. Bridge trainer name is `3DSLINK`, within the seven-character limit.

The optional [experimental remote mode](remote-trading.md) installs a gate before the upstream engine confirms its trade. A private room admits one pinned bridge identity per role. Once the source bridge validates the current Switch offer, both trusted bridges accept that revision automatically. The relay carries encrypted snapshots; each bridge retains recovery records. Remote mode must be selected explicitly and still requires hardware timing validation.

The pinned engine durably writes a receipt when `CONFIRM_FINISH_TRADE` commits the exchange. The bridge verifies that receipt against the accepted offer and releases the source result immediately; the Switch-side process may continue cancelling the trade menu and closing its link afterward. A receipt is never inferred from process exit alone.

## Transaction states

```text
prepared -> running -> received -> ready -> applied
                |          |
                v          v
             uncertain  import_blocked
```

`start` is idempotent by a client-generated 128-bit ID. A restart never launches a running transaction again. The service recovers a valid receipt or marks the transaction uncertain. A live process timeout also requires manual inspection. A process exit code is not sufficient to generate a replacement save.

Confirmation checks the original selected record and the incoming Pokemon before producing `result.sav`. Egg, mail, trade-evolution and pre-National-Dex incompatibilities block automatic import rather than discarding the received file. The latter cases currently need manual recovery.

On SD, the app writes a full original backup and persistent pending record before a trade can start. On result application it:

1. Verifies the download hash and the backup hash.
2. Checks the current source still matches the original, or already matches the result.
3. Writes and reads back a temporary result beside the source.
4. Renames the source to a transaction-specific `.trade-old-<id>` backup.
5. Renames the result into place and verifies it again.
6. Acknowledges application to the PC, then removes the pending record.

A crash between renames leaves a recognizable old-save backup. A dropped acknowledgement leaves an already-applied result that recovery recognizes by hash. Filesystem corruption or physical removal of the SD card can still require manual recovery; software cannot guarantee power-loss atomicity across two consoles and an SD card.

## LAN protocol

All requests require `Authorization: Bearer <32 hexadecimal characters>` and a bounded `Content-Length`. The 3DS uses HTTP/1.0 with a fresh connection per request. Bodies are limited to 128 KiB. Binary requests/results are raw saves; other responses are UTF-8 lines. Unknown name glyphs are display-only substitutions.

| Method and path | Body / response |
| --- | --- |
| `GET /v1/health` | Protocol version, backend mode |
| `POST /v1/saves` | Raw save -> save ID, family, trainer, public TID, warning, mode |
| `GET /v1/saves/<id>/boxes/<0..13>` | 30 lines of absolute box slot, tab, label |
| `PUT /v1/trades/<id>` | Save ID and absolute slot on separate lines -> state |
| `GET /v1/trades/<id>` | State |
| `POST /v1/trades/<id>/start` | Idempotently start one trade |
| `POST /v1/trades/<id>/confirm` | User confirms console save; produce result |
| `GET /v1/trades/<id>/result` | Verified raw result save |
| `POST /v1/trades/<id>/applied` | Client acknowledges local replacement |

The first seven state-response lines retain the local protocol, including empty fields: state, message, received summary, backend mode, result SHA-256, offered art, received art. Each art field contains a National Dex number and shiny flag separated by a tab. The first five fields remain compatible with older clients. Missing art in older bridge responses or transactions uses a generic Pokeball. The client animates the active link while running and reveals the incoming sprite only after a received state. It polls every two seconds; this is not synchronized with individual Switch animation frames. Synchronous HTTP requests can pause the animation while the bridge responds. Filenames supplied by a client never become server filesystem paths. Only checked IDs select server-owned paths.

The CLI exclusively locks its data directory. Manual resolution requires stopping the service first. An unexpected server termination may leave a child trade process alive; inspect and stop it before operator reconciliation. The bridge must not be exposed beyond a trusted LAN.

Remote responses append an eighth field containing the current offer revision or pairing verification code. The remote-only verify and approve endpoints require that exact value; cancel requests retain ambiguous exchanges for recovery. Local clients may ignore the appended field.
