"""Experimental native MCU mode-4 speed hook: Unicorn memory ONLY.

Not a flashable MCU firmware: the trampoline at 0xF000 has no allocated space
in the OEM MCU image, needs approved linker/layout and complete hardware tests.
Mode 2/3/11 paths execute OEM instructions; mode 4 is a proposed SSM-only
reserved value, not an OEM-supported mode. No motor or brake tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from bwpatcher.mi5pro_integration import MCU_BASE, McuOriginal
from bwpatcher.mi5pro_research import AnalysisError
from bwpatcher.ssm_firmware import ORIGINALS

HOOK_FILE_OFFSET = 0x1D0D6
HOOK_RUNTIME_ADDRESS = HOOK_FILE_OFFSET - MCU_BASE
NEXT_RUNTIME_ADDRESS = HOOK_RUNTIME_ADDRESS + 4
SSM_CONTINUE_ADDRESS = 0x1D0F2 - MCU_BASE
TEST_ONLY_CODE_ADDRESS = 0xF000
# Raw target is approx 30 km/h using original factor 20.9; not calibrated on hardware.
EXPERIMENTAL_30_RAW = int(30 * 20.9)
ORIGINAL_INSNS = bytes.fromhex("11780b29")


@dataclass(frozen=True)
class CompiledMcuHook:
    redirect: bytes
    routine: bytes
    target_raw: int
    firmware_image_created: bool = False
    safe_to_flash: bool = False


def compile_mcu_hook(original_mcu: bytes) -> CompiledMcuHook:
    """Build native Thumb control flow for a hypothetical independent mode 4."""
    from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
    if sha256(original_mcu).hexdigest() != ORIGINALS["mcu"]["sha256"]:
        raise AnalysisError("Exaktes MCU-Original erforderlich.")
    if original_mcu[HOOK_FILE_OFFSET:HOOK_FILE_OFFSET+4] != ORIGINAL_INSNS:
        raise AnalysisError("MCU Originalinstruktionen am Hook unterscheiden sich.")
    asm = f"""
        ldrb r1, [r2]
        cmp r1, #4
        bne original
        movw r1, #{EXPERIMENTAL_30_RAW}
        strh r1, [r4, #0x14]
        b.w {SSM_CONTINUE_ADDRESS}
    original:
        cmp r1, #11
        bx lr
    """
    ks = Ks(KS_ARCH_ARM,KS_MODE_THUMB)
    try:
        raw,_=ks.asm(asm,addr=TEST_ONLY_CODE_ADDRESS)
        jump,_=ks.asm(f"bl {TEST_ONLY_CODE_ADDRESS}",addr=HOOK_RUNTIME_ADDRESS)
    except Exception as exc:
        raise AnalysisError(f"MCU Thumb-Assembler: {exc}") from exc
    if len(jump)!=4 or len(raw)>0x100:
        raise AnalysisError("Ungueltige MCU Probe.")
    return CompiledMcuHook(bytes(jump),bytes(raw),EXPERIMENTAL_30_RAW)


class McuHookProbe(McuOriginal):
    """MCU original plus an emulator-only 0xF000 page for executable testing."""
    def _instruction(self, uc, address, size, user):
        if TEST_ONLY_CODE_ADDRESS <= address < TEST_ONLY_CODE_ADDRESS + 0x100:
            self.min_sp = min(self.min_sp, uc.reg_read(self.sp))
            return
        return super()._instruction(uc,address,size,user)

    def __init__(self, image: bytes):
        super().__init__(image)
        self.staged = compile_mcu_hook(image)
        self.uc.mem_map(TEST_ONLY_CODE_ADDRESS, 0x1000, 5)
        self.uc.mem_write(TEST_ONLY_CODE_ADDRESS, self.staged.routine)
        self.uc.mem_write(HOOK_RUNTIME_ADDRESS, self.staged.redirect)
