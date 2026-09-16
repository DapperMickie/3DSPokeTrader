# Automate private trusted-room exchanges

Remote trading is a private, self-hosted tool for cooperative friends rather than a public matchmaking service. Each high-entropy room admits exactly one source bridge identity and one Switch bridge identity. Bridges pin the peer identity locally, retain end-to-end encryption, and reject identity replacement.

The encrypted channel is trusted as soon as the room peer is pinned. The source bridge validates every current Switch offer against the source save and automatically accepts valid revisions; a changed offer must pass validation again. The Switch bridge commits only after it receives the matching validation and automatic acceptance from the source bridge.

The Switch browser control page, short-code comparison, offer buttons, and final saved button are removed from the normal flow. A matching receipt is released automatically only after the Switch-side trade process exits. Missing or mismatched receipts remain uncertain and require manual recovery; radio trades are never automatically repeated after interruption.

After both bridges durably record a successful exchange and source-save application, they reuse the same pinned room and identities. They clear only the completed exchange fields and files; pending or uncertain exchanges continue to block reuse.

This decision supersedes the manual verification and bilateral approval controls in ADR 0001 and ADR 0002. Local trading remains unchanged and remote mode remains an explicit experimental opt-in.
