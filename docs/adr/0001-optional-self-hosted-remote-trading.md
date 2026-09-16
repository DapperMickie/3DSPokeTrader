# Keep remote trading optional and self-hosted

Local trading remains the default. Friends may explicitly configure a relay they host themselves to enable private remote trades; PokeTrader will not require a project-operated service or provide public player discovery for this release. This puts relay setup on users in exchange for keeping the existing local workflow independent of hosted infrastructure.

The relay operator must provide a reachable server address and HTTPS; a Docker deployment example will document setup. Bridges connect outward. Trade contents are encrypted between the bridges so the relay operator cannot read Pokemon or trainer information. Players compare and confirm a short verification phrase through an existing independent chat for each new pairing. The relay owner issues access credentials separately from room codes.

The relay forwards messages without durable offline delivery. Both bridges retain recovery records and must reconnect to finish interrupted exchanges; restarting or replacing the relay must not erase the exchange. This avoids making recovery depend on relay storage, at the cost of requiring both bridges to return online.
