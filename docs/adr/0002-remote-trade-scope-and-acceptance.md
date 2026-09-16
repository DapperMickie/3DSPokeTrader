# Start with cooperative 3DS to Switch exchanges

The first remote release targets 3DS and Switch trades between cooperative friends, with Switch to Switch deferred until its protocol requirements have been investigated. Both players must accept the exact offers before either side commits; normal exchanges must not require temporary deposits. Recovery must handle interruptions, but the design does not promise cheat prevention, guaranteed fairness, or atomic saving across consoles.

Approvals bind to the exact pair of offers, and changing either offer clears both approvals. Once either side may have committed, the exchange must not expire automatically; both bridges retain recovery data and block conflicting trades until resolution.

At decision time, the backend did not expose a pre-commit remote approval step. Inspection of the pinned upstream engine showed that it receives the Switch party and selected slot before automatically confirming. The experimental implementation now adds an asynchronous approval gate; hardware validation of delayed approval, cancellation, reselection and disconnects remains required.

Source: [Pinned trade engine](https://github.com/tornadus/frlg-ldn-trade/blob/13809c21b6e992097f98453b7cbc9e2bc30bbf7c/frlgsim/trade.py).
