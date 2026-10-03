"""115 download wire format, adapted from SheltonZhu/115driver (MIT).

Copyright (c) 2022-2024 SheltonZhu. See THIRD_PARTY_NOTICES.md.
"""

import base64
import secrets


_MODULUS = int(
    "8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b86021"
    "36477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad633"
    "8c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f1"
    "0a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683", 16)
_SEED = bytes.fromhex(
    "f0e569aebfdcbf8a1a45e8be7da673b8de8fe7c445da86c49b648b146ab4f1aa"
    "3801359e26692c86006b4fa5363462a62a966818f24afdbd6b978f4d8f8913b7"
    "6c8e93ed0e0d483ed72f88d8fefe7e8650954fd1eb832634db667b9c7e9d7a81"
    "32eab633de3aa95934663baaba816048b9d5819cf86c8477ff5478265fbee81e"
    "369f34805c452c9b76d51b8fccc3b8f5")
_CLIENT_KEY = bytes.fromhex("7806ad4c33865d184c013f46")


def _derive(seed, length):
    return bytes(((seed[i] + _SEED[length * i]) & 255) ^ _SEED[length * (length - i - 1)]
                 for i in range(length))


def _xor(data, key):
    prefix = len(data) % 4
    return bytes(value ^ key[(i if i < prefix else i - prefix) % len(key)]
                 for i, value in enumerate(data))


def encode(data, key):
    transformed = key + _xor(_xor(data, _derive(key, 4))[::-1], _CLIENT_KEY)
    encrypted = bytearray()
    for offset in range(0, len(transformed), 117):
        chunk = transformed[offset:offset + 117]
        padding = bytes(secrets.randbelow(255) + 1 for _ in range(125 - len(chunk)))
        block = b"\0\2" + padding + b"\0" + chunk
        encrypted.extend(pow(int.from_bytes(block), 65537, _MODULUS).to_bytes(128))
    return base64.b64encode(encrypted).decode("ascii")


def decode(data, key):
    encrypted = base64.b64decode(data, validate=True)
    if not encrypted or len(encrypted) % 128:
        raise ValueError("Invalid 115 encrypted response")
    decrypted = bytearray()
    for offset in range(0, len(encrypted), 128):
        block = pow(int.from_bytes(encrypted[offset:offset + 128]), 65537, _MODULUS).to_bytes(128)
        separator = block.find(b"\0", 2)
        if block[:2] != b"\0\1" or separator < 10:
            raise ValueError("Invalid 115 RSA response padding")
        decrypted.extend(block[separator + 1:])
    if len(decrypted) < 16:
        raise ValueError("Invalid 115 response key")
    return _xor(_xor(decrypted[16:], _derive(decrypted[:16], 12))[::-1], _derive(key, 4))
