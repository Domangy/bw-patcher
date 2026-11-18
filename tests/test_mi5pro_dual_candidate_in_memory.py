"""Complete firmware-container-to-Unicorn evidence, OFFLINE ONLY."""
from hashlib import sha256
import os
from pathlib import Path

import pytest

from bwpatcher.mi5pro_dual_candidate_in_memory import build_dual_research_candidate
from bwpatcher.mi5pro_mcu_candidate_in_memory import McuResearchCandidateEmulator
from bwpatcher.mi5pro_ssm_native_prototype import BleNativeHarness
from bwpatcher.mi5pro_research import inspect_ble
from bwpatcher.ssm_firmware import inspect_mcu, ORIGINALS


@pytest.fixture(scope="module")
def originals():
    directory = os.environ.get("MI5PRO_FIRMWARE_DIR")
    if not directory:
        pytest.skip("Lokale Originalbilder erforderlich.")
    root = Path(directory)
    return ((root / "ble_2.7.0_0015.bin").read_bytes(),
            (root / "mcu_0007.bin").read_bytes())


@pytest.fixture(scope="module")
def pair(originals):
    return build_dual_research_candidate(*originals)


def test_both_wrappers_are_structurally_valid_but_untrusted(originals, pair):
    ble, mcu = originals
    decoded = inspect_ble(pair.ble_image)
    report = inspect_mcu(pair.mcu.image)
    assert len(decoded.app) == 181612
    assert report["checksums_valid"]
    assert report["es_code_size"] == 0xAEB0
    assert sha256(ble).hexdigest() == ORIGINALS["ble"]["sha256"]
    assert sha256(mcu).hexdigest() == ORIGINALS["mcu"]["sha256"]
    assert pair.ble_original_sha256 == ORIGINALS["ble"]["sha256"]
    assert pair.oem_firmware_signatures_validated is False
    assert pair.hardware_validated is False
    assert pair.safe_to_flash is False


def test_full_pair_executes_three_double_clicks_and_exit_in_unicorn(originals, pair):
    original_ble, original_mcu = originals
    b = BleNativeHarness(original_ble, fake_eligible=True, candidate_ble=pair.ble_image)
    controller = McuResearchCandidateEmulator(original_mcu, pair.mcu)
    limits = controller.select_limits(b"60556")
    assert limits["sport_raw"] == 417

    frame = b.send_controller_frame()
    assert frame[3] == 0x23
    controller.consume_mode(frame)
    assert controller.speed_selection(3) == 417

    events = b.click_pairs(3)
    assert [event["event"] for event in events] == [2, 2, 2]
    assert b.native_clock_ticks == 276  # generated entirely by Thumb instructions
    assert b.active
    assert b.local_oem_mode == 3
    frame = b.send_controller_frame()
    assert frame[3] == 0x24
    assert frame[-2] == sum(frame[:-2]) & 0xff
    controller.consume_mode(frame)
    assert controller.read(0x20000229, 1) == b"\x04"
    assert controller.speed_selection(4) == 627

    b.click_pairs(1)
    assert b.native_clock_ticks == 368
    assert not b.active
    frame = b.send_controller_frame()
    assert frame[3] == 0x23
    controller.consume_mode(frame)
    assert controller.speed_selection(3) == 417


def test_unapproved_flag_never_activates_pair(originals, pair):
    original_ble, original_mcu = originals
    b = BleNativeHarness(original_ble, fake_eligible=False, candidate_ble=pair.ble_image)
    b.click_pairs(3)
    assert not b.active
    ctrl = McuResearchCandidateEmulator(original_mcu, pair.mcu)
    ctrl.select_limits(b"60556")
    frame = b.send_controller_frame()
    assert frame[3] == 0x23
    ctrl.consume_mode(frame)
    assert ctrl.speed_selection(3) == 417
