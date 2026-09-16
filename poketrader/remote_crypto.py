"""Authenticated bridge snapshots. Relay credentials never become encryption keys."""
from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization


PEER_ROLES = {
    "source": "switch",
    "switch": "source",
    "switch-a": "switch-b",
    "switch-b": "switch-a",
    "source-a": "source-b",
    "source-b": "source-a",
}


def encode(data):
    return base64.b64encode(data).decode("ascii")


def decode(value):
    return base64.b64decode(value, validate=True)


def new_identity():
    return encode(X25519PrivateKey.generate().private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption()))


class Channel:
    def __init__(self, private, peer, room, role):
        if role not in PEER_ROLES:
            raise ValueError("Invalid remote role")
        key = X25519PrivateKey.from_private_bytes(decode(private))
        self.public = encode(key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        first = role in ("source", "switch-a", "source-a")
        transcript = json.dumps(["PokeTrader/remote/1", room,
            self.public if first else peer,
            peer if first else self.public], separators=(",", ":")).encode()
        self.context = hashlib.sha256(transcript).digest()
        self.key = HKDF(algorithm=hashes.SHA256(), length=32, salt=self.context,
                       info=b"PokeTrader snapshots").derive(key.exchange(
                           X25519PublicKey.from_public_bytes(decode(peer))))
        self.role = role
        # 64-bit comparison code. Confirmation through an independent channel is mandatory.
        raw = hashlib.sha256(self.key + self.context + b"verify").hexdigest()[:16].upper()
        self.phrase = "-".join(raw[i:i+4] for i in range(0, 16, 4))

    def seal(self, sequence, value):
        nonce = os.urandom(12)
        aad = self.context + self.role.encode() + str(sequence).encode()
        return dict(sequence=sequence, payload=encode(nonce + AESGCM(self.key).encrypt(
            nonce, json.dumps(value, separators=(",", ":")).encode(), aad)))

    def open(self, envelope):
        sequence = envelope["sequence"]
        if type(sequence) is not int or sequence < 1:
            raise ValueError("Invalid snapshot sequence")
        data = decode(envelope["payload"])
        peer_role = PEER_ROLES[self.role]
        plain = AESGCM(self.key).decrypt(data[:12], data[12:],
            self.context + peer_role.encode() + str(sequence).encode())
        value = json.loads(plain)
        if not isinstance(value, dict):
            raise ValueError("Invalid snapshot")
        return value


def public_key(private):
    return encode(X25519PrivateKey.from_private_bytes(decode(private)).public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw))
