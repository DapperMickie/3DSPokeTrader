# Remote trading design interview

The user confirmed shared understanding and authorized implementation on `codex/remote-trading-design`. See [setup and validation](remote-trading.md) for the experimental implementation.

## Agreed user controls

The 3DS player uses the 3DS app. The Switch player uses a browser interface served by their local bridge, accessible from a phone or computer on their network, to join a private room, inspect offers and approve the exchange.

For each new pairing, both players compare a short verification phrase through their existing chat and confirm that it matches. The relay owner issues an access credential to friends, separate from room codes; the first release has no accounts or registration system.

The Switch player explicitly confirms in their browser that the console has saved and exited the trading room before the replacement save is released to the 3DS player. A protocol receipt alone does not establish console persistence.

Remote offer presentation must match the existing local implementation, without adding the proposed moves, held-item, IV or EV inspection views. The local trade screen uses species/nickname summaries and species sprites with shiny variants; the existing box selection details remain available for selecting the source Pokemon. The Switch supplies its party records through the local trade protocol, and its selected slot identifies the offered record; this does not require reading its save file.

The current local trade screen reveals the incoming Pokemon only after a receipt. Remote trading must present the offer before commitment to satisfy the agreed bilateral approval requirement, while reusing the current presentation style and information. Approval still binds to the full record.

## Cancellation and recovery

Either player may cancel before commitment, clearing both approvals and closing the proposed exchange. Once commitment may have started, cancellation becomes a recovery request and cannot promise to undo the Switch trade.

Bridges automatically resume exchanging status and retained results after reconnecting. They must never automatically repeat a radio trade, and any outstanding Switch-save confirmation remains pending for the Switch player.

## Compatibility and validation

Remote trading retains the current supported Pokemon scope, including restrictions on eggs, held mail, trade evolutions and source-save compatibility. Validate both offers before allowing approval or commitment.

Internet trading remains experimental until physical consoles pass separate-network trades and tests for delayed approval, changed offers, bridge restarts and disconnects around commitment.

## Branch isolation

Remote-trading design and subsequent implementation belong on a separate branch. The design branch is `codex/remote-trading-design`; main must not receive this work without a later merge decision.

## Remaining design closure

The design interview is complete. Exact approval-wait limits remain a hardware experiment, not a settled protocol guarantee.

## Protocol prerequisite

The pinned engine automatically confirms after receiving the selected Switch slot. Add an asynchronous approval gate before confirmation while continuing the simulator's appropriate local protocol processing. Ordinary overworld held-key keepalives stop at trade-menu entry and must not simply be emitted throughout the wait.

Hardware tests must establish how long the console can wait and verify decline, changed selection and disconnect behavior. The proposed gate remains unproven on hardware.
