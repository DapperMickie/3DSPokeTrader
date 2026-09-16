# Host a PokeTrader relay

Remote PokeTrader modes use a small self-hosted relay so both bridges make
outbound HTTPS connections. Local 3DS-to-Switch trading does not use a relay.

The relay forwards end-to-end encrypted bridge snapshots. It cannot read the
Pokemon or trainer records, and it stores no durable trade history. Bridge data
directories remain the recovery record and must not be deleted while an
exchange is pending.

## Docker Compose

Use a server with a public DNS name and reachable TCP ports 80 and 443. Install
Docker Engine and Compose, then run from the repository root:

```sh
mkdir -p deploy/relay/secrets
python3 -c 'import secrets; from pathlib import Path; Path("deploy/relay/secrets/relay-credential").write_text(secrets.token_hex(32))'
printf 'RELAY_HOST=relay.example.com\n' > deploy/relay/.env
docker compose -f deploy/relay/compose.yml --env-file deploy/relay/.env up -d --build
```

Replace `relay.example.com` with your DNS name and point its DNS record at the
server. Caddy obtains the HTTPS certificate and proxies to the relay inside the
Compose network. Do not publish the relay's internal port or expose a bridge's
local port 8765 to the internet.

Copy the generated credential file privately to every participating bridge.
The relay credential is separate from the room code and should not be posted or
embedded in a release.

## Existing HTTPS reverse proxy

Run the relay on loopback:

```sh
poke-trader relay --credential-file relay-credential --bind 127.0.0.1 --port 8780
```

Proxy `/v1/exchange` from the public HTTPS hostname to `127.0.0.1:8780`. Relay
redirects are rejected, and bridges validate the server certificate with their
operating-system trust store.

## Portainer

`deploy/relay/portainer-compose.yml` builds the repository and joins the
existing `robsengamingproxy` network as `pokerelay:8780`. It creates a
64-character credential in the persistent `relay_data` volume on first start.
Read it once from the container and store it on the participating bridges.

The container starts as root only to initialize the Docker-managed volume. Its
root filesystem is read-only, Linux capabilities are dropped, and privilege
escalation is disabled.

## Operation and recovery

The relay limits rooms, message size, and concurrent requests. Idle in-memory
room entries expire after ten minutes. This does not cancel a trade or erase its
recovery state because bridges resend their current encrypted snapshots after
reconnecting.

Restarting or replacing the relay is safe. Both bridges must reconnect to
finish an interrupted exchange because the relay has no offline mailbox. Keep
the same bridge configuration and data directories until the exchange reaches
a completed or manually reconciled state.

After upgrading to a release that adds room roles, rebuild and restart the
relay before using those roles:

```sh
docker compose -f deploy/relay/compose.yml --env-file deploy/relay/.env up -d --build
```
