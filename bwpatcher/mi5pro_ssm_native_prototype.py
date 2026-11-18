"""Native-code Mi5Pro SSM prototype, exclusively in Unicorn emulators.

Actual ARM Thumb hooks modify BLE click handling, OEM UART frame transmission,
and MCU limit selection within the two original firmware emulators.
The UART connection between the two emulator instances is HOST-SIMULATED:
no real serial link, verified clock/safety inputs, allocated target memory,
flashable OTA package, or controller hardware validation exists.
"""
from __future__ import annotations

from unicorn import UC_HOOK_CODE

from bwpatcher.mi5pro_emulator import OriginalAppEmulator
from bwpatcher.mi5pro_mcu_hook_experimental import McuHookProbe
from bwpatcher.mi5pro_research import APP_BASE, inspect_ble, AnalysisError
from bwpatcher.mi5pro_thumb_hook_experimental import (
    compile_hook, HOOK, TX_HOOK, CAVE, RAM_CANDIDATE,
)

REGION_TEST_PREFIX = b"60556"


class BleNativeHarness:
    def __init__(self, original_ble: bytes, *, fake_eligible: bool):
        app = inspect_ble(original_ble).app
        patch = compile_hook(app)
        self.original_ble = original_ble
        self.machine = OriginalAppEmulator(app)
        self.machine.uc.mem_write(APP_BASE + HOOK, patch.branch)
        self.machine.uc.mem_write(APP_BASE + CAVE, patch.thumb + patch.tx_thumb)
        self.machine.uc.mem_write(APP_BASE + TX_HOOK, patch.tx_branch)
        self.machine.uc.mem_write(
            RAM_CANDIDATE,bytes((0,0,1 if fake_eligible else 0,0,0,0,0,0,0,0))
        )
        self.machine.uc.mem_write(self.machine.INFO+1,b"\x03")
        self.machine.uc.mem_write(self.machine.INFO+0xE,b"\x01")
        self.tick = 0
        self.oem_mode_calls = 0
        self.machine.uc.hook_add(UC_HOOK_CODE, self._on_code)
        original_tick = self.machine.dispatch_tick

        def clocked_tick(level: bool):
            self.tick += 1
            self.machine.uc.mem_write(
                RAM_CANDIDATE+4,(self.tick & 0xFFFF).to_bytes(2,"little")
            )
            return original_tick(level)
        self.machine.dispatch_tick = clocked_tick

    def _on_code(self, uc, address, size, unused):
        if address == APP_BASE + 0x80AA:
            self.oem_mode_calls += 1

    @property
    def active(self) -> bool:
        return bool(self.machine.uc.mem_read(RAM_CANDIDATE+1,1)[0])

    @property
    def local_oem_mode(self) -> int:
        return int(self.machine.uc.mem_read(self.machine.INFO+1,1)[0])

    def click_pairs(self, count: int, *, pause_ticks: int = 60) -> list:
        return self.machine.click_trace(2*count,pair_pause_ticks=pause_ticks,dispatch=True)

    def send_controller_frame(self) -> bytes:
        """Use OEM UART frame builder, then NATIVE Thumb TX intercept in emulator."""
        if self.local_oem_mode not in (2,3,11):
            raise AnalysisError("Unbekannter OEM-Modus im BLE-Demo.")
        self.machine.uc.mem_write(self.machine.INFO,b"\x02")
        self.machine.uc.mem_write(self.machine.INFO+0x1D,b"\x01")
        self.machine.call(0x3940,stubs={APP_BASE+0x9300:"uart"})
        frames=[bytes.fromhex(v) for kind,v in self.machine.calls if kind=="uart"]
        if len(frames)!=1 or len(frames[0])!=12:
            raise AnalysisError("Kein eindeutiger 12-Byte UART Modusframe.")
        frame=frames[0]
        if (frame[:3]!=b"\x51\x10\x07" or frame[-1]!=0xAE
                or frame[-2] != (sum(frame[:-2]) & 0xFF)):
            raise AnalysisError("SSM UART-Hook lieferte einen ungueltigen Frame.")
        return frame


def synthetic_mcu_bridge(ble: BleNativeHarness, mcu: bytes) -> dict:
    """Execute native modified BLE+MCU code; transfer bytes ONLY in host emulator."""
    observed=ble.local_oem_mode
    frame=ble.send_controller_frame()
    transmitted=frame[3]&15
    controller=McuHookProbe(mcu)
    limits=controller.select_limits(REGION_TEST_PREFIX)
    controller.consume_mode(frame)
    actual=controller.read(0x20000229,1)[0]
    result=controller.speed_selection(actual)
    return {
        "ble_local_mode":observed,
        "ble_native_active":ble.active,
        "native_uart_frame_hex":frame.hex(),
        "synthetic_transmitted_mode":transmitted,
        "mcu_received_mode":actual,
        "mcu_native_target_raw":result,
        "mcu_original_sport_raw":limits["sport_raw"],
        "uart_payload_modified_by_native_thumb":True,
        "hardware_transport_tested":False,
        "uart_bridge_is_host_simulated":True,
        "image_created":False,
        "safe_to_flash":False,
    }
