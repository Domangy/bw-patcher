"""Offline construction of an MCU research candidate, not an OTA release.

This builds bytes only in memory. No files, devices, or flash writes. A valid
ES32 CRC is not a digital signature. Mode 4 bypasses an original speed cap
and is unvalidated on motor, brake, thermal and battery hardware.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from bwpatcher.mi5pro_integration import MCU_BASE, MCU_END, McuOriginal
from bwpatcher.mi5pro_mcu_hook_experimental import (
    HOOK_FILE_OFFSET,
    ORIGINAL_INSNS,
    compile_mcu_hook,
)
from bwpatcher.ssm_firmware import ORIGINALS, crc16, inspect_mcu
from bwpatcher.mi5pro_research import AnalysisError


@dataclass(frozen=True)
class McuResearchCandidate:
    image: bytes
    stub_runtime_address: int
    stub_length: int
    es_code_size: int
    crc_valid: bool
    original_image_sha256: str
    firmware_authentication_proven: bool = False
    on_device_tested: bool = False
    safe_to_flash: bool = False


def build_mcu_research_candidate(original: bytes) -> McuResearchCandidate:
    """Add a 20-byte hook into an original 240-byte FF tail in memory only.

    The tail is package padding, not evidence of accepted extra executable
    memory on the actual MCU or proof of signature/update acceptance.
    """
    if len(original) != ORIGINALS["mcu"]["size"] or (
        sha256(original).hexdigest() != ORIGINALS["mcu"]["sha256"]
    ):
        raise AnalysisError("MCU Forschungsprototyp verlangt das exakte Original.")
    layout = inspect_mcu(original)
    if not layout["checksums_valid"]:
        raise AnalysisError("Original MCU CRC ist ungueltig.")
    head = layout["es_header_offset"]
    code = layout["es_code_offset"]
    old_size = layout["es_code_size"]
    entry = code + old_size
    if (head != 0x19800 or code != MCU_BASE or old_size != MCU_END - MCU_BASE
            or entry != 0x24710):
        raise AnalysisError("Unbekanntes ES32-Layout; kein Speicherpatch.")
    stub = compile_mcu_hook(original, code_address=old_size)
    rounded = (old_size + len(stub.routine) + 15) & ~15
    end = code + rounded
    if rounded > 0xB000 or end > len(original):
        raise AnalysisError("MCU Programmueberlauf.")
    if original[entry:end] != b"\xff" * (end - entry):
        raise AnalysisError("Kein leeres ES32-Endpadding an diesem Bereich.")
    if original[HOOK_FILE_OFFSET:HOOK_FILE_OFFSET + 4] != ORIGINAL_INSNS:
        raise AnalysisError("MCU Originalinstruktionen geaendert.")
    altered = bytearray(original)
    altered[HOOK_FILE_OFFSET:HOOK_FILE_OFFSET + 4] = stub.redirect
    altered[entry:entry + len(stub.routine)] = stub.routine
    altered[head + 6:head + 8] = rounded.to_bytes(2, "big")
    altered[head + 0x30:head + 0x32] = bytes.fromhex(crc16(altered, code, rounded))
    altered[0x0A:0x0C] = bytes.fromhex(crc16(altered, head, len(altered) - head))
    altered = bytes(altered)
    verdict = inspect_mcu(altered)
    if (not verdict["checksums_valid"]
            or verdict["es_code_size"] != rounded
            or verdict["es_code_offset"] != code
            or len(altered) != len(original)):
        raise AnalysisError("Rekonstruiertes ES32-Paket ist nicht konsistent.")
    return McuResearchCandidate(
        image=altered, stub_runtime_address=old_size,
        stub_length=len(stub.routine), es_code_size=rounded,
        crc_valid=True, original_image_sha256=sha256(original).hexdigest(),
    )


class McuResearchCandidateEmulator(McuOriginal):
    """Emulates the candidate's bytes as part of its loaded MCU program image."""

    def __init__(self, original_mcu: bytes, candidate: McuResearchCandidate):
        if candidate.firmware_authentication_proven or candidate.safe_to_flash:
            raise AnalysisError("Firmwarefreigabe wird nicht unterstellt.")
        super().__init__(original_mcu)
        inspected = inspect_mcu(candidate.image)
        if not inspected["checksums_valid"]:
            raise AnalysisError("Kandidatencontainer ist inkonsistent.")
        if candidate.original_image_sha256 != sha256(original_mcu).hexdigest():
            raise AnalysisError("Kandidat stammt nicht von diesem Original.")
        self.candidate_end = inspected["es_code_size"]
        self.candidate_start = self.candidate_end - (
            (candidate.stub_length + 15) & ~15
        )
        if self.candidate_start != candidate.stub_runtime_address:
            raise AnalysisError("Unbekannte MCU-Stubeinbaustelle.")
        self.uc.mem_write(0, candidate.image[MCU_BASE:MCU_BASE + self.candidate_end])

    def _instruction(self, uc, address, size, user):
        if MCU_END - MCU_BASE <= address < getattr(self, "candidate_end", 0):
            self.min_sp = min(self.min_sp, uc.reg_read(self.sp))
            return
        return super()._instruction(uc, address, size, user)
