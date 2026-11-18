"""Tests of offline release evidence tooling, no controller or OTA writes."""
import hashlib
from pathlib import Path

import pytest

from bwpatcher.mi5pro_offline_suite import ROOT, file_hashes, run_suite
from bwpatcher.ssm_firmware import ORIGINALS


def test_refuses_missing_originals_and_does_not_execute_pytest(tmp_path):
    report, status = run_suite(tmp_path)
    assert status == 2
    assert report["originals_verified"] is False
    assert report["originals_unchanged"] is True
    assert "pytest" not in report["checks"]
    assert report["release_ready"] is False
    assert report["hardware_validated"] is False
    assert report["flashable_ssm_firmware_created"] is False


def test_refuses_unrecognized_firmware_files(tmp_path):
    path = tmp_path / "originale"
    path.mkdir()
    for name in ("mcu_0007.bin", "ble_2.7.0_0015.bin"):
        (path / name).write_bytes(b"unrelated")
    before = file_hashes(path)
    report, status = run_suite(tmp_path)
    assert status == 2
    assert before == file_hashes(path) == report["firmware_hashes_after"]


def test_identity_hashes_on_local_originals_if_available():
    folder = ROOT / "originale"
    if not all((folder / x).is_file() for x in ("mcu_0007.bin", "ble_2.7.0_0015.bin")):
        pytest.skip("Lokale Originaldateien nicht vorhanden.")
    report, status = run_suite(ROOT, skip_tests=True)
    assert status == 0
    assert report["originals_verified"] is True
    assert report["originals_unchanged"] is True
    for key, name in (("mcu", "mcu_0007.bin"), ("ble", "ble_2.7.0_0015.bin")):
        assert report["firmware_hashes_before"][name] == ORIGINALS[key]["sha256"]
    assert report["release_ready"] is False
