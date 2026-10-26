"""Tuya LAN framing and authenticated media; no credentials leave memory."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import struct
import zlib

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7


def encrypt(key: bytes, data: bytes, iv: bytes | None = None) -> bytes:
    pad = PKCS7(128).padder()
    padded = pad.update(data) + pad.finalize()
    cipher = Cipher(algorithms.AES(key), modes.ECB() if iv is None else modes.CBC(iv)).encryptor()
    return cipher.update(padded) + cipher.finalize()


def decrypt(key: bytes, data: bytes, iv: bytes | None = None) -> bytes:
    if not data or len(data) % 16:
        raise ValueError("Invalid encrypted block length")
    cipher = Cipher(algorithms.AES(key), modes.ECB() if iv is None else modes.CBC(iv)).decryptor()
    plain = cipher.update(data) + cipher.finalize()
    pad = PKCS7(128).unpadder()
    return pad.update(plain) + pad.finalize()


def pack_signal(key: bytes, seq: int, cmd: int, payload: dict | None = None) -> bytes:
    body = encrypt(key, json.dumps(payload, separators=(",", ":")).encode()) if payload is not None else b""
    if cmd == 7:
        body = b"3.3" + bytes(12) + body
    frame = struct.pack("!IIII", 0x55AA, seq, cmd, len(body) + 8) + body
    return frame + struct.pack("!II", zlib.crc32(frame), 0xAA55)


def unpack_signal(key: bytes, frame: bytes) -> tuple[int, dict]:
    prefix, _, cmd, length = struct.unpack_from("!IIII", frame)
    if prefix != 0x55AA or not 8 <= length <= 1024 * 1024 or len(frame) != 16 + length:
        raise ValueError("Invalid LAN frame")
    crc, suffix = struct.unpack_from("!II", frame, len(frame) - 8)
    if suffix != 0xAA55 or zlib.crc32(frame[:-8]) != crc:
        raise ValueError("Invalid LAN checksum")
    body = frame[16:-8]
    if len(body) % 16 in (3, 4):
        body = body[4:]
    if body.startswith(b"3.3"):
        body = body[15:]
    if not body:
        return cmd, {}
    plain = decrypt(key, body)
    try:
        value = json.loads(plain)
    except (ValueError, UnicodeError):
        return cmd, {}  # IPC acknowledgements may carry opaque binary data.
    return cmd, value if isinstance(value, dict) else {}


def seal(key: bytes, plain: bytes) -> bytes:
    iv = secrets.token_bytes(16)
    return iv + encrypt(key, plain, iv)


def open_media(key: bytes, data: bytes) -> tuple[int, bytes]:
    if len(data) < 32:
        raise ValueError("Short media message")
    msg = decrypt(key, data[16:], data[:16])
    if len(msg) < 40 or msg[:4] == b"\x78\x56\x34\x12":
        return 0, b""
    cmd = struct.unpack_from("<I", msg)[0]
    sub = msg[32:]
    offset = 16 if len(sub) >= 16 and struct.unpack_from("<I", sub)[0] == len(sub) - 4 else 8
    return cmd, sub[offset:]


def authenticate(key: bytes, data: bytes) -> bytes:
    return hmac.digest(key, data, hashlib.sha1)
