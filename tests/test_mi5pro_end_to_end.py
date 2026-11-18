"""Offline End-to-end checks. Never communicate with or flash a scooter."""
import hashlib
import os
from pathlib import Path

import pytest

from bwpatcher.mi5pro_end_to_end import emulate_full_chain
from bwpatcher.mi5pro_research import AnalysisError
from bwpatcher.ssm_firmware import ORIGINALS


def test_unknown_images_are_rejected_before_any_emulation():
    with pytest.raises(AnalysisError):
        emulate_full_chain(b"not BLE", b"not MCU")


@pytest.mark.parametrize("invalid", [None, 1, "yes"])
def test_only_explicit_boolean_demo_intent_is_accepted(invalid):
    with pytest.raises(TypeError):
        emulate_full_chain(b"", b"", demo_intent=invalid)


@pytest.fixture(scope="module")
def originals():
    directory = os.environ.get("MI5PRO_FIRMWARE_DIR")
    if not directory:
        pytest.skip("Originale lokal erforderlich, niemals in Git ablegen.")
    pytest.importorskip("unicorn")
    base = Path(directory)
    ble = (base / "ble_2.7.0_0015.bin").read_bytes()
    mcu = (base / "mcu_0007.bin").read_bytes()
    assert hashlib.sha256(ble).hexdigest() == ORIGINALS["ble"]["sha256"]
    assert hashlib.sha256(mcu).hexdigest() == ORIGINALS["mcu"]["sha256"]
    return ble, mcu


def test_real_original_modes_do_not_infer_activation_without_intent(originals):
    report = emulate_full_chain(*originals)
    assert report["three_distinct_doubles_verified"]
    assert [x["dashboard_mode"] for x in report["path"]] == [11, 2, 3]
    assert [x["mcu_mode"] for x in report["path"]] == [11, 2, 3]
    assert report["model_state"] == "normal"
    assert report["model_request_kmh"] is None
    assert report["final_original_limit_raw"] == report["original_sport_limit_raw"]
    assert not report["ssm_firmware_created"] and not report["flashable"]


def test_demo_intent_does_not_prove_actual_controller_30kmh(originals):
    report = emulate_full_chain(*originals, demo_intent=True)
    assert report["model_state"] == "active"
    assert report["model_request_kmh"] == 30
    assert report["path"][-1]["model_actions"] == ["ssm_activate"]
    assert report["final_original_limit_raw"] == report["original_sport_limit_raw"]
    assert not report["real_applied_30_kmh_proven"]
    assert not report["real_limit_acknowledgement_proven"]
    assert not report["flashable"]


def test_emulation_does_not_change_originals(originals):
    before = tuple(hashlib.sha256(x).digest() for x in originals)
    emulate_full_chain(*originals, demo_intent=True)
    assert before == tuple(hashlib.sha256(x).digest() for x in originals)
