"""Known Xiaomi OTA variant checks; originals never committed with tests."""
import hashlib
import os
from pathlib import Path

import pytest

from bwpatcher.mi5pro_cloud import (
    CLOUD_MD5, CLOUD_SHA256, CLOUD_SIZE,
    CloudBLEMismatch, extract_original_ble,
)
from bwpatcher.mi5pro_research import APP_SHA256, inspect_ble
from bwpatcher.ssm_firmware import ORIGINALS


@pytest.mark.parametrize("kind", ["empty", "same_size", "other"])
def test_rejects_unrecognized_download(kind):
    data = {"empty": b"", "same_size": b"x" * CLOUD_SIZE,
            "other": b"invalid firmware"}[kind]
    with pytest.raises(CloudBLEMismatch):
        extract_original_ble(data)


def test_rejects_nonbytes():
    with pytest.raises(TypeError):
        extract_original_ble(bytearray(CLOUD_SIZE))


@pytest.fixture(scope="module")
def official_cloud_file():
    path = os.environ.get("MI5PRO_CLOUD_DOWNLOAD")
    if not path:
        pytest.skip("Xiaomi OTA aus eigenem Konto ist privat und nicht Teil des Repositorys.")
    data = Path(path).read_bytes()
    assert len(data) == CLOUD_SIZE
    assert hashlib.md5(data).hexdigest() == CLOUD_MD5
    assert hashlib.sha256(data).hexdigest() == CLOUD_SHA256
    return data


def test_real_cloud_download_extracts_identical_original(official_cloud_file):
    original = extract_original_ble(official_cloud_file)
    assert len(original) == ORIGINALS["ble"]["size"]
    assert hashlib.sha256(original).hexdigest() == ORIGINALS["ble"]["sha256"]
    assert hashlib.sha256(inspect_ble(original).app).hexdigest() == APP_SHA256


@pytest.mark.parametrize("position", [0, 12, 4096, 152551, 152552, 153889])
def test_rejects_corrupted_cloud_bytes(official_cloud_file, position):
    corrupted = bytearray(official_cloud_file)
    corrupted[position] ^= 1
    with pytest.raises(CloudBLEMismatch):
        extract_original_ble(bytes(corrupted))


def test_rejects_truncated_and_appended_download(official_cloud_file):
    for data in (official_cloud_file[:-1], official_cloud_file + b"x"):
        with pytest.raises(CloudBLEMismatch):
            extract_original_ble(data)
