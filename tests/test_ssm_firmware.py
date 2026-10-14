#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Synthetische Strukturtests; Originale optional und ausschliesslich lokal."""

import os
from pathlib import Path

import pytest

from bwpatcher.__main__ import main as patch_cli
from bwpatcher.core import CorePatcher
from bwpatcher.detect import detect_bytes
from bwpatcher.ssm import SSMUnavailableError
from bwpatcher.ssm_firmware import assess_firmware, crc16, disassemble_mcu, inspect_mcu, main
from bwpatcher import utils


def synthetic_mcu():
    data = bytearray(b"\xff" * 0x1800)
    data[:4] = (0x1000).to_bytes(4, "big")
    data[0x12:0x16] = b"0108"
    data[0x22:0x2e] = b"000700010001"
    data[0xc06:0xc08] = (0x100).to_bytes(2, "big")
    data[0xc10:0xc20] = b"SZMC-ES-ZM-0283M"
    data[0xc30:0xc32] = bytes.fromhex(crc16(data, 0xc80, 0x100))
    data[0xa:0xc] = bytes.fromhex(crc16(data, 0xc00, len(data) - 0xc00))
    return data


def test_crc_known_vector_and_existing_implementation():
    assert crc16(b"123456789", 0, 9) == "31c3"
    assert CorePatcher._compute_checksum(b"123456789", 0, 9).hex() == "31c3"


@pytest.mark.parametrize("offset,size", [(-1, 1), (0, 0), (8, 2), (10, 1), (0, 10)])
def test_crc_rejects_truncated_or_invalid_ranges(offset, size):
    with pytest.raises(ValueError):
        crc16(b"123456789", offset, size)


def test_structure_validation_is_not_original_identification():
    data = synthetic_mcu()
    before = bytes(data)
    structure = inspect_mcu(data)
    assert structure["checksums_valid"] is True
    assert detect_bytes(data).best == "mi5pro"
    result = assess_firmware(data, "mcu")
    assert result["original_identified"] is False
    assert result["ssm_patch_available"] is False
    assert bytes(data) == before


def test_changed_body_is_detected_by_crc():
    data = synthetic_mcu()
    data[0xc90] ^= 1
    result = inspect_mcu(data)
    assert result["checksums_valid"] is False
    assert result["outer_crc"]["computed"] != result["outer_crc"]["stored"]
    assert result["inner_crc"]["computed"] != result["inner_crc"]["stored"]


@pytest.mark.parametrize("mutation", [
    lambda d: d[:0x700],
    lambda d: d[:-1],
    lambda d: d + b"\x00",
    lambda d: d[:0xc10] + b"?" * 16 + d[0xc20:],
])
def test_malformed_package_is_rejected(mutation):
    with pytest.raises(ValueError):
        inspect_mcu(mutation(synthetic_mcu()))


def test_ambiguous_inner_header_is_rejected():
    data = synthetic_mcu()
    data[0xd10:0xd20] = b"SZMC-ES-ZM-0283M"
    with pytest.raises(ValueError, match="eindeutig"):
        inspect_mcu(data)


def test_inner_crc_cannot_silently_read_past_eof():
    data = synthetic_mcu()
    data[0xc06:0xc08] = b"\xff\xff"
    with pytest.raises(ValueError, match="ausserhalb"):
        inspect_mcu(data)


@pytest.mark.parametrize("component", ["mcu", "ble"])
def test_unknown_files_are_never_whitelisted(component):
    result = assess_firmware(b"unbekannte Firmware", component)
    assert not result["original_identified"]
    assert not result["ssm_patch_available"]


def test_unknown_component_is_rejected():
    with pytest.raises(ValueError):
        assess_firmware(b"", "dashboard")


def test_disassembly_sites_cannot_be_used_on_unknown_firmware():
    with pytest.raises(ValueError, match="exakte Original"):
        disassemble_mcu(synthetic_mcu())


def test_package_crc_does_not_cover_first_code_area():
    data = synthetic_mcu()
    data[0x900] ^= 1
    assert inspect_mcu(data)["checksums_valid"]
    assert not assess_firmware(data, "mcu")["original_identified"]


@pytest.mark.parametrize("web", [True, False])
@pytest.mark.parametrize("experimental", [True, False])
@pytest.mark.parametrize("patches", [
    ["ssm"], ["ssm=30"], ["sls=30", "ssm", "chk"], [" SSM =1"],
])
def test_ssm_rejected_before_any_patcher_instantiation(monkeypatch, web, experimental, patches):
    def forbidden(*args):
        pytest.fail("Kein Patcher darf bei SSM instanziiert werden.")
    monkeypatch.setattr(utils, "import_module", forbidden)
    data = bytearray(b"original")
    with pytest.raises(SSMUnavailableError):
        utils.patch_firmware("mi5pro", data, patches, web=web, allow_experimental=experimental)
    assert data == b"original"


@pytest.mark.parametrize("preexisting_output", [False, True])
def test_cli_ssm_failure_does_not_write_output(tmp_path, capsys, preexisting_output):
    infile, outfile = tmp_path / "in.bin", tmp_path / "out.bin"
    infile.write_bytes(b"original")
    if preexisting_output:
        outfile.write_bytes(b"bestehende Ausgabe")
    assert patch_cli(["mi5pro", str(infile), str(outfile), "ssm", "--experimental"]) == 1
    assert "keine SSM-Firmware" in capsys.readouterr().err
    if preexisting_output:
        assert outfile.read_bytes() == b"bestehende Ausgabe"
    else:
        assert not outfile.exists()


def test_audit_cli_identifies_unknown_file_without_modifying_it(tmp_path, capsys):
    path = tmp_path / "test.bin"
    path.write_bytes(b"original")
    assert main(["--mcu", str(path)]) == 1
    assert '"ssm_patch_available": false' in capsys.readouterr().out
    assert path.read_bytes() == b"original"


def original_path(filename):
    directory = os.environ.get("MI5PRO_FIRMWARE_DIR")
    if not directory:
        pytest.skip("Originalfirmware nicht im Repository; MI5PRO_FIRMWARE_DIR setzen.")
    path = Path(directory) / filename
    if not path.is_file():
        pytest.fail(f"Explizit angegebenes Original fehlt: {path}")
    return path


@pytest.mark.parametrize("component,filename", [
    ("mcu", "mcu_0007.bin"), ("ble", "ble_2.7.0_0015.bin"),
])
def test_downloaded_original_identity(component, filename):
    data = original_path(filename).read_bytes()
    result = assess_firmware(data, component)
    assert result["original_identified"]
    assert not result["ssm_patch_available"]
    if component == "mcu":
        assert result["structure"]["checksums_valid"]
        assert result["structure"]["package_version_field"] == "0108"
        assert result["issues"] == []


def test_existing_checksum_fix_leaves_original_identical():
    data = original_path("mcu_0007.bin").read_bytes()
    assert utils.patch_firmware("mi5pro", data, ["chk"]) == data


def test_literal_pool_references_are_reproducible_on_exact_original():
    data = original_path("mcu_0007.bin").read_bytes()
    instructions = {i["file_offset"]: i for i in disassemble_mcu(data)}
    assert instructions["0x1d0c8"]["literal_value"] == "0x20000229"
    assert instructions["0x1d0d0"]["literal_value"] == "0x20000326"
    assert instructions["0x1d13a"]["literal_value"] == "0x20000324"
    assert instructions["0x203cc"]["literal_value"] == "0x20000229"


@pytest.mark.parametrize("patch,sites", [
    ("sls=30", [(0x1d140, 2), (0x1d2f0, 4)]),
    ("sld=30", [(0x1d13c, 2), (0x1d318, 4)]),
])
def test_legacy_speed_patches_only_touch_previously_observed_sites(patch, sites):
    data = original_path("mcu_0007.bin").read_bytes()
    assert assess_firmware(data, "mcu")["original_identified"]
    output = utils.patch_firmware("mi5pro", data, [patch, "chk"])
    assert output != data and len(output) == len(data)
    # Dies prüft Regressionen im bestehenden Patch, keine Schutzfreigabe.
    allowed = set()
    for start, size in sites + [(0xa, 2), (0x19830, 2), (0x1d0e8, 10)]:
        allowed.update(range(start, start + size))
    changes = {i for i, (a, b) in enumerate(zip(data, output)) if a != b}
    assert changes <= allowed
    assert inspect_mcu(output)["checksums_valid"]
