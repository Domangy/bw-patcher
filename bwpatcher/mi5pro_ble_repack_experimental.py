"""Experimental Mi5Pro BLE image repacker for in-memory format research.

The return value is NOT a signed, accepted, safe, or flashable OTA update.
It is deliberately NOT exposed through any CLI, GUI, or firmware export path.
No interaction with physical devices occurs.
"""
from __future__ import annotations

import hashlib
import lzma
import struct

from bwpatcher.mi5pro_research import (
    APP_SHA256, BLOCK_LAST, BLOCK_MORE, AnalysisError,
    control_header, inspect_ble, normal_image_digest,
)
from bwpatcher.ssm_firmware import ORIGINALS

BLOCK_SIZE = 0x4000
COMPRESSED_HEADER_SIZE = 96


def experimental_repack_ble(original_ble: bytes, prospective_app: bytes) -> bytes:
    """Recompress an identified BLE APP into a structurally parsable test image.

    This proves only internal image consistency, not executable compatibility,
    original ROM Patch compatibility, secure-boot trust, or safe behaviour.
    No bytes are written to disk, and this API is not called by the patcher.
    """
    if type(original_ble) is not bytes or type(prospective_app) is not bytes:
        raise TypeError("Beide Eingaben muessen bytes sein.")
    if (len(original_ble) != ORIGINALS["ble"]["size"]
            or hashlib.sha256(original_ble).hexdigest() != ORIGINALS["ble"]["sha256"]):
        raise AnalysisError("Nur das exakt bekannte BLE-Original ist zugelassen.")
    decoded = inspect_ble(original_ble)
    current = decoded.app
    if hashlib.sha256(current).hexdigest() != APP_SHA256:
        raise AnalysisError("APP-Hash des Originals stimmt nicht.")
    if len(prospective_app) != len(current):
        raise AnalysisError("Geaenderte APP-Laenge ohne Linker-/Speicherbeweis gesperrt.")
    # Treat the embedded normal-image control header as immutable, except its SHA.
    if prospective_app[:0x400] != current[:0x400]:
        raise AnalysisError("APP-Header darf nicht veraendert werden.")

    app = bytearray(prospective_app)
    digest = normal_image_digest(app)["computed"]
    app[0x174:0x194] = bytes.fromhex(digest)
    if not normal_image_digest(app)["valid"]:
        raise AnalysisError("APP-Pruefsumme konnte nicht neu erzeugt werden.")

    offset = decoded.report["compressed_offset"]
    header = bytearray(original_ble[offset:offset + COMPRESSED_HEADER_SIZE])
    compressed = bytearray()
    for begin in range(0, len(app), BLOCK_SIZE):
        plain = bytes(app[begin:begin + BLOCK_SIZE])
        encoded = bytearray(lzma.compress(
            plain, format=lzma.FORMAT_ALONE,
            filters=[{"id": lzma.FILTER_LZMA1, "dict_size": 4096}],
        ))
        # Python liblzma writes -1 (unknown size) plus an EOS marker. Changing
        # that header to a known size corrupts this particular stream. The
        # original OEM LZMA stream used a known size: firmware-acceptance of
        # this alternative representation has NOT been demonstrated.
        if len(encoded) > 0xFFFF:
            raise AnalysisError("LZMA-Block ueberschreitet das 16-Bit-Laengenfeld.")
        last = begin + BLOCK_SIZE >= len(app)
        compressed += struct.pack(
            "<IHH", BLOCK_LAST if last else BLOCK_MORE, len(plain), len(encoded),
        )
        compressed += encoded
    compressed += b"\xff" * (-len(compressed) % 4)

    # Preserve UUID, image ID, flags and encryption declaration from OEM header.
    struct.pack_into("<I", header, 8, len(compressed))
    header[36:68] = hashlib.sha256(compressed).digest()
    output = original_ble[:offset] + bytes(header) + bytes(compressed)
    rebuilt = inspect_ble(output)
    if rebuilt.app != bytes(app):
        raise AnalysisError("Neu verpacktes APP konnte nicht fehlerfrei dekodiert werden.")
    if rebuilt.report["patch_digest"] != decoded.report["patch_digest"]:
        raise AnalysisError("Originaler ROM-Patch wurde unerwartet veraendert.")
    return output
