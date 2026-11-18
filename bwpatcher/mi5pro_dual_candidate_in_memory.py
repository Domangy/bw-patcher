"""Build structurally consistent BLE and MCU research bytes in memory only.

No digital signature, hardware validation, scooter link, OTA output or
installer is provided. These byte arrays MUST NOT be flashed to a vehicle.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from bwpatcher.mi5pro_ble_repack_experimental import experimental_repack_ble
from bwpatcher.mi5pro_mcu_candidate_in_memory import (
    McuResearchCandidate, build_mcu_research_candidate,
)
from bwpatcher.mi5pro_research import inspect_ble, AnalysisError
from bwpatcher.mi5pro_thumb_hook_experimental import (
    compile_hook, HOOK, TX_HOOK, CAVE, CLOCK_HOOK, CLOCK_CODE_OFF,
    CLOCK_LITERAL_OFF, RAM_CANDIDATE,
)


@dataclass(frozen=True)
class DualResearchCandidate:
    ble_image: bytes
    mcu: McuResearchCandidate
    ble_original_sha256: str
    oem_firmware_signatures_validated: bool = False
    hardware_validated: bool = False
    safe_to_flash: bool = False


def build_dual_research_candidate(
    original_ble: bytes, original_mcu: bytes,
) -> DualResearchCandidate:
    """Build candidate images in memory, verifying both internal formats."""
    app = inspect_ble(original_ble).app
    staged = compile_hook(app)
    rebuilt = experimental_repack_ble(original_ble, staged.app)
    app_check = inspect_ble(rebuilt).app
    for offset, expected in (
        (HOOK, staged.branch),
        (TX_HOOK, staged.tx_branch),
        (CAVE, staged.thumb + staged.tx_thumb),
        (CLOCK_HOOK, staged.clock_branch),
        (CLOCK_CODE_OFF, staged.clock_thumb),
        (CLOCK_LITERAL_OFF, RAM_CANDIDATE.to_bytes(4,"little")),
    ):
        if app_check[offset:offset + len(expected)] != expected:
            raise AnalysisError("BLE ARM-Thumb-Code im neu aufgebauten Paket inkonsistent.")
    mcu = build_mcu_research_candidate(original_mcu)
    if sha256(rebuilt).digest() == sha256(original_ble).digest():
        raise AnalysisError("BLE Forschungsimage wurde nicht veraendert.")
    return DualResearchCandidate(
        ble_image=rebuilt, mcu=mcu,
        ble_original_sha256=sha256(original_ble).hexdigest(),
    )
