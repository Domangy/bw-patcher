"""Executable native Thumb proof tests, NOT scooter/OTA validation."""
from pathlib import Path
import os
import pytest

from bwpatcher.mi5pro_ssm_native_prototype import BleNativeHarness, synthetic_mcu_bridge
from bwpatcher.mi5pro_thumb_hook_experimental import compile_hook
from bwpatcher.mi5pro_mcu_hook_experimental import compile_mcu_hook, McuHookProbe
from bwpatcher.mi5pro_research import inspect_ble, AnalysisError
from bwpatcher.mi5pro_integration import McuOriginal


@pytest.fixture(scope="module")
def originals():
    folder=os.environ.get("MI5PRO_FIRMWARE_DIR")
    if not folder:
        pytest.skip("Proprietäre Originalfirmware nur lokal getestet.")
    root=Path(folder)
    return ((root/"ble_2.7.0_0015.bin").read_bytes(),
            (root/"mcu_0007.bin").read_bytes())


def test_thumb_binaries_contain_actual_redirects_without_firmware_export(originals):
    ble,mcu=originals
    app=inspect_ble(ble).app
    staged=compile_hook(app)
    mcu_staged=compile_mcu_hook(mcu)
    assert 4 == len(staged.branch)
    assert 0 < len(staged.thumb) <=125
    assert len(staged.tx_branch)==4
    assert len(staged.thumb)+len(staged.tx_thumb)<=130
    assert len(mcu_staged.redirect)==4
    assert mcu_staged.target_raw==627
    assert staged.safe_to_flash is False
    assert mcu_staged.firmware_image_created is False
    assert app!=staged.app  # genuine ARM instruction bytes staged in memory


def test_three_oem_double_clicks_enter_and_single_double_exits_native(originals):
    ble,mcu=originals
    b=BleNativeHarness(ble,fake_eligible=True)
    original=synthetic_mcu_bridge(b,mcu)
    assert original["ble_native_active"] is False
    assert original["mcu_native_target_raw"] == 417
    trace=b.click_pairs(3)
    assert [row["event"] for row in trace]==[2,2,2]
    assert [row["mode_after"] for row in trace]==[11,2,3]
    assert b.oem_mode_calls==3
    assert b.active
    active=synthetic_mcu_bridge(b,mcu)
    assert active["ble_local_mode"]==3
    assert active["synthetic_transmitted_mode"]==4
    assert active["native_uart_frame_hex"].startswith("51100724")
    assert active["uart_payload_modified_by_native_thumb"] is True
    assert active["hardware_transport_tested"] is False
    assert active["mcu_received_mode"]==4
    assert active["mcu_native_target_raw"]==627
    assert active["uart_bridge_is_host_simulated"] is True
    assert active["safe_to_flash"] is False
    b.click_pairs(1)
    assert not b.active
    assert b.local_oem_mode==3
    assert b.oem_mode_calls==3  # next double does not call stock mode cycle
    normal=synthetic_mcu_bridge(b,mcu)
    assert normal["mcu_native_target_raw"]==417
    assert normal["native_uart_frame_hex"].startswith("51100723")


def test_ineligible_snapshot_prevents_activation(originals):
    ble,mcu=originals
    b=BleNativeHarness(ble,fake_eligible=False)
    b.click_pairs(3)
    assert b.oem_mode_calls==3
    assert b.local_oem_mode==3
    assert not b.active
    assert synthetic_mcu_bridge(b,mcu)["mcu_native_target_raw"]==417


def test_excessive_gap_prevents_activation(originals):
    ble,_=originals
    b=BleNativeHarness(ble,fake_eligible=True)
    trace=b.click_pairs(3,pause_ticks=200)
    assert [item["event"] for item in trace]==[2,2,2]
    assert not b.active
    assert b.oem_mode_calls==3


def test_real_arm_mcu_original_modes_remain_unchanged(originals):
    _,mcu=originals
    stock=McuOriginal(mcu)
    patch=McuHookProbe(mcu)
    stock.select_limits(b"60556")
    patch.select_limits(b"60556")
    for mode in (11,2,3):
        assert patch.speed_selection(mode)==stock.speed_selection(mode)
    assert stock.speed_selection(4)==208
    assert patch.speed_selection(4)==627




def test_start_in_drive_does_not_activate_ssm(originals):
    ble,_=originals
    b=BleNativeHarness(ble,fake_eligible=True)
    b.machine.uc.mem_write(b.machine.INFO+1,bytes((2,)))
    b.click_pairs(3)
    assert b.local_oem_mode==2
    assert not b.active
    assert b.oem_mode_calls==3


def test_repeated_activation_after_exit(originals):
    ble,mcu=originals
    b=BleNativeHarness(ble,fake_eligible=True)
    b.click_pairs(3)
    assert b.active
    b.click_pairs(1)
    assert not b.active
    b.click_pairs(3)
    assert b.active
    assert b.local_oem_mode==3
    assert synthetic_mcu_bridge(b,mcu)["mcu_native_target_raw"]==627

def test_unrecognized_images_are_rejected():
    with pytest.raises(AnalysisError):
        compile_mcu_hook(b"invalid")
    with pytest.raises(AnalysisError):
        compile_hook(b"invalid")
