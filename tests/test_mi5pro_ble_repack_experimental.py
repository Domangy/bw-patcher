"""Structural-only BLE rebuilding tests. Never export or flash images."""
import hashlib
import os
from pathlib import Path

import pytest

from bwpatcher.mi5pro_ble_repack_experimental import experimental_repack_ble
from bwpatcher.mi5pro_research import AnalysisError, inspect_ble


@pytest.fixture(scope="module")
def original_ble():
    folder = os.environ.get("MI5PRO_FIRMWARE_DIR")
    if not folder:
        pytest.skip("Lokale Originaldatei fuer proprietaere Paketpruefung erforderlich.")
    return (Path(folder) / "ble_2.7.0_0015.bin").read_bytes()


def test_noop_rebuild_is_structurally_valid_but_not_assumed_flashable(original_ble):
    source_app = inspect_ble(original_ble).app
    result = experimental_repack_ble(original_ble, source_app)
    assert inspect_ble(result).app == source_app
    # The stock LZMA streams are not byte-identical to Python LZMA output.
    # Any changed container would need OEM boot/signature and hardware checks.
    assert result != original_ble


def test_byte_change_survives_roundtrip_in_memory_without_export(original_ble):
    source_app = inspect_ble(original_ble).app
    different = bytearray(source_app)
    different[0x9000] ^= 0x01  # synthetic mutation; NOT an SSM payload!
    result = experimental_repack_ble(original_ble, bytes(different))
    rebuilt = inspect_ble(result).app
    assert rebuilt[0x9000] == different[0x9000]
    assert rebuilt[0x9001:] == source_app[0x9001:]
    assert hashlib.sha256(rebuilt).digest() != hashlib.sha256(source_app).digest()


@pytest.mark.parametrize("kind", ["empty", "same_size", "other"])
def test_unknown_base_rejected(kind):
    bad = {"empty": b"", "same_size": b"x" * 152552,
           "other": b"not firmware"}[kind]
    with pytest.raises(AnalysisError):
        experimental_repack_ble(bad, b"")


def test_app_header_mutation_rejected(original_ble):
    app = bytearray(inspect_ble(original_ble).app)
    app[0x28] ^= 1
    with pytest.raises(AnalysisError, match="Header"):
        experimental_repack_ble(original_ble, bytes(app))


def test_app_length_change_rejected(original_ble):
    app = inspect_ble(original_ble).app
    with pytest.raises(AnalysisError, match="Laenge"):
        experimental_repack_ble(original_ble, app + b"X")


def test_nonbytes_input_rejected():
    with pytest.raises(TypeError):
        experimental_repack_ble(bytearray(0), b"")
