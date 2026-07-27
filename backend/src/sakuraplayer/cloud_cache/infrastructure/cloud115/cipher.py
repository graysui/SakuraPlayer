from __future__ import annotations

import base64
import json
from typing import Any

from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Problem

# Adapted from the GPL-3.0-only source identified in NOTICE.md. Only the
# downurl RSA/XOR protocol is retained; upload encryption is intentionally absent.
RSA_N = 0x8686980C0F5A24C4B9D43020CD2C22703FF3F450756529058B1CF88F09B8602136477198A6E2683149659BD122C33592FDB5AD47944AD1EA4D36C6B172AAD6338C3BB6AC6227502D010993AC967D1AEF00F0C8E038DE2E4D3BC2EC368AF2E9F10A6F1EDA4F7262F136420C07C331B871BF139F74F3010E3C4FE57DF3AFB71683
RSA_E = 0x10001
G_KEY_L = b"\x78\x06\xad\x4c\x33\x86\x5d\x18\x4c\x01\x3f\x46"
RSA_KEY = b"\x8d\xa5\xa5\x8d"
_RAND_KEY_ZEROS = b"\x00" * 16
_G_KTS = bytes(
    (
        0xF0,
        0xE5,
        0x69,
        0xAE,
        0xBF,
        0xDC,
        0xBF,
        0x8A,
        0x1A,
        0x45,
        0xE8,
        0xBE,
        0x7D,
        0xA6,
        0x73,
        0xB8,
        0xDE,
        0x8F,
        0xE7,
        0xC4,
        0x45,
        0xDA,
        0x86,
        0xC4,
        0x9B,
        0x64,
        0x8B,
        0x14,
        0x6A,
        0xB4,
        0xF1,
        0xAA,
        0x38,
        0x01,
        0x35,
        0x9E,
        0x26,
        0x69,
        0x2C,
        0x86,
        0x00,
        0x6B,
        0x4F,
        0xA5,
        0x36,
        0x34,
        0x62,
        0xA6,
        0x2A,
        0x96,
        0x68,
        0x18,
        0xF2,
        0x4A,
        0xFD,
        0xBD,
        0x6B,
        0x97,
        0x8F,
        0x4D,
        0x8F,
        0x89,
        0x13,
        0xB7,
        0x6C,
        0x8E,
        0x93,
        0xED,
        0x0E,
        0x0D,
        0x48,
        0x3E,
        0xD7,
        0x2F,
        0x88,
        0xD8,
        0xFE,
        0xFE,
        0x7E,
        0x86,
        0x50,
        0x95,
        0x4F,
        0xD1,
        0xEB,
        0x83,
        0x26,
        0x34,
        0xDB,
        0x66,
        0x7B,
        0x9C,
        0x7E,
        0x9D,
        0x7A,
        0x81,
        0x32,
        0xEA,
        0xB6,
        0x33,
        0xDE,
        0x3A,
        0xA9,
        0x59,
        0x34,
        0x66,
        0x3B,
        0xAA,
        0xBA,
        0x81,
        0x60,
        0x48,
        0xB9,
        0xD5,
        0x81,
        0x9C,
        0xF8,
        0x6C,
        0x84,
        0x77,
        0xFF,
        0x54,
        0x78,
        0x26,
        0x5F,
        0xBE,
        0xE8,
        0x1E,
        0x36,
        0x9F,
        0x34,
        0x80,
        0x5C,
        0x45,
        0x2C,
        0x9B,
        0x76,
        0xD5,
        0x1B,
        0x8F,
        0xCC,
        0xC3,
        0xB8,
        0xF5,
    )
)
_RSA_BLOCK_SIZE = 128
_RSA_MESSAGE_SIZE = 117


def _rsa_key(rand_key: bytes, length: int) -> bytes:
    output = bytearray(length)
    table_index = 0
    reverse_index = length * (length - 1)
    for index in range(length):
        output[index] = _G_KTS[reverse_index] ^ (
            (rand_key[index] + _G_KTS[table_index]) & 0xFF
        )
        reverse_index -= length
        table_index += length
    return bytes(output)


def _xor(data: bytes, key: bytes) -> bytes:
    output = bytearray()
    remainder = len(data) & 3
    for index in range(remainder):
        output.append(data[index] ^ key[index])
    offset = remainder
    while offset < len(data):
        size = min(len(key), len(data) - offset)
        for index in range(size):
            output.append(data[offset + index] ^ key[index])
        offset += size
    return bytes(output)


def rsa_encode(data: bytes) -> bytes:
    transformed = _xor(_xor(data, RSA_KEY)[::-1], G_KEY_L)
    buffer = _RAND_KEY_ZEROS + transformed
    encrypted = bytearray()
    for offset in range(0, len(buffer), _RSA_MESSAGE_SIZE):
        chunk = buffer[offset : offset + _RSA_MESSAGE_SIZE]
        padding = b"\x00" + b"\x02" * (126 - len(chunk)) + b"\x00" + chunk
        value = pow(int.from_bytes(padding, "big"), RSA_E, RSA_N)
        encrypted.extend(value.to_bytes(_RSA_BLOCK_SIZE, "big"))
    return base64.b64encode(encrypted)


def rsa_decode(ciphertext: bytes | str) -> bytes:
    try:
        encoded = (
            ciphertext.encode("ascii") if isinstance(ciphertext, str) else ciphertext
        )
        raw = base64.b64decode(encoded, validate=True)
    except (UnicodeEncodeError, ValueError):
        raise Cloud115Problem("cloud115_protocol_error") from None
    if not raw or len(raw) % _RSA_BLOCK_SIZE:
        raise Cloud115Problem("cloud115_protocol_error")

    decoded = bytearray()
    for offset in range(0, len(raw), _RSA_BLOCK_SIZE):
        value = pow(
            int.from_bytes(raw[offset : offset + _RSA_BLOCK_SIZE], "big"),
            RSA_E,
            RSA_N,
        )
        block = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
        try:
            separator = block.index(b"\x00")
        except ValueError:
            raise Cloud115Problem("cloud115_protocol_error") from None
        decoded.extend(block[separator + 1 :])
    if len(decoded) < 16:
        raise Cloud115Problem("cloud115_protocol_error")
    rand_key = bytes(decoded[:16])
    body = _xor(_xor(bytes(decoded[16:]), _rsa_key(rand_key, 12))[::-1], RSA_KEY)
    return body


def encrypt_payload(payload: dict[str, str]) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return rsa_encode(body)


def decrypt_response(ciphertext: str) -> dict[str, Any]:
    try:
        value = json.loads(rsa_decode(ciphertext))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise Cloud115Problem("cloud115_protocol_error") from None
    if not isinstance(value, dict):
        raise Cloud115Problem("cloud115_protocol_error")
    return value


__all__ = ["decrypt_response", "encrypt_payload", "rsa_decode", "rsa_encode"]
