#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Begrenzte Ausführung identifizierter Originalroutinen, ohne Gerätezugriff.

Unicorn ist nur für diesen Forschungsweg erforderlich. Emulierte GPIO-Eingaben
und abgefangene Ausgaben sind keine Messungen an einem Scooter. Unbekannte ROM-
Aufrufe, Speicherzugriffe und überschrittene Instruktionsbudgets brechen ab.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

from bwpatcher.mi5pro_research import APP_BASE, APP_SHA256, AnalysisError, inspect_ble


class OriginalAppEmulator:
    INFO = 0x20826C
    KEY_STATE = 0x208624
    DISPLAY = 0x2088B0

    def __init__(self, app: bytes):
        if hashlib.sha256(app).hexdigest() != APP_SHA256:
            raise AnalysisError("Emulation verlangt das exakt untersuchte entpackte APP.")
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        from unicorn.arm_const import (
            UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
            UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
            UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
            UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
        )
        self.r0, self.r1, self.r2 = UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2
        self.sp, self.lr, self.pc = UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
        self.saved_registers = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
            UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.uc.mem_map(APP_BASE, (len(app) + 4095) & ~4095, 5)  # read/execute
        self.uc.mem_write(APP_BASE, app)
        self.uc.mem_map(0x200000, 0x10000)
        self.uc.mem_map(0x40001000, 0x1000)
        self.uc.mem_map(0x10000000, 0x1000)
        self.uc.mem_map(0x11000, 0x1000)
        for index, reg in enumerate(self.saved_registers):
            self.uc.reg_write(reg, 0xA4B50000 + index * 0x101)
        self.app_size = len(app)
        self.calls = []
        self.writes = []
        self.stubs = {}
        self.failure = None
        self.returned = False
        self._allow_gpio_output = False
        self.uc.hook_add(UC_HOOK_CODE, self._instruction)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self._write)

    def _instruction(self, uc, address, size, _):
        if address == APP_BASE + 0x8300 and uc.reg_read(self.r0):
            self.calls.append(("key_event", uc.reg_read(self.r0)))
        if address == APP_BASE + 0x8550:
            self.calls.append(("original_mode_dispatch", 1))
        if address == 0x10000000:
            self.returned = True
            uc.emu_stop()
        elif address in self.stubs:
            kind = self.stubs[address]
            if kind == "uart":
                if uc.reg_read(self.r0) != 0x40011000:
                    self.failure = "UART-Aufruf verwendet eine unerwartete Peripheriebasis."
                    uc.emu_stop()
                    return
                length = uc.reg_read(self.r2)
                if not 0 < length <= 150:
                    self.failure = "UART-Frame überschreitet die Analysegrenze."
                    uc.emu_stop()
                    return
                value = bytes(uc.mem_read(uc.reg_read(self.r1), length)).hex()
            else:
                value = uc.reg_read(self.r0) & 255
            self.calls.append((kind, value))
            uc.reg_write(self.r0, 0)
            uc.reg_write(self.pc, uc.reg_read(self.lr))
        elif not APP_BASE + 0x400 <= address < APP_BASE + self.app_size:
            self.failure = f"Nicht modellierter externer Aufruf bei {address:#x}."
            uc.emu_stop()

    def _write(self, uc, access, address, size, value, _):
        self.writes.append((address, size, value))
        gpio_output = self._allow_gpio_output and address == 0x40001000 and size == 4
        if not gpio_output and not 0x200000 <= address < address + size <= 0x210000:
            self.failure = f"Nicht erlaubte Firmware-Schreiboperation bei {address:#x}."
            uc.emu_stop()

    def call(self, offset: int, arg: int = 0, *, stubs=None, budget=20000,
             gpio_output=False) -> int:
        from unicorn import UcError

        if type(budget) is not int or not 0 < budget <= 1000000:
            raise AnalysisError("Ein endliches positives Instruktionsbudget ist erforderlich.")
        if type(offset) is not int or offset % 2 or not 0x400 <= offset < self.app_size:
            raise AnalysisError("Ungültiger oder nicht ausgerichteter APP-Einstieg.")
        self.calls.clear()
        self.writes.clear()
        self.stubs = stubs or {}
        self._allow_gpio_output = gpio_output
        self.returned = False
        self.failure = None
        self.uc.reg_write(self.sp, 0x20FFF0)
        self.uc.reg_write(self.lr, 0x10000001)
        self.uc.reg_write(self.r0, arg)
        saved = [self.uc.reg_read(reg) for reg in self.saved_registers]
        try:
            self.uc.emu_start((APP_BASE + offset) | 1, 0, count=budget)
        except UcError as exc:
            raise AnalysisError(f"Originalausführung abgebrochen: {exc}") from exc
        finally:
            self.stubs = {}
            self._allow_gpio_output = False
        if self.failure:
            raise AnalysisError(self.failure)
        if not self.returned:
            raise AnalysisError("Originalroutine kehrt innerhalb des Budgets nicht zurück.")
        self.last_abi = {
            "stack_balanced": self.uc.reg_read(self.sp) == 0x20FFF0,
            "callee_saved_preserved": saved == [self.uc.reg_read(reg) for reg in self.saved_registers],
        }
        if not all(self.last_abi.values()):
            raise AnalysisError("Der geprüfte AAPCS-Register-/Stackvertrag wurde verletzt.")
        return self.uc.reg_read(self.r0)

    def button_tick(self, gpio_high: bool) -> int:
        # Originaler Pin-ID-Mapper: 0x21 -> Bit 29; echter GPIO-Leser nutzt +0x50.
        self.uc.mem_write(0x40001050, struct.pack("<I", int(gpio_high) << 29))
        return self.call(0x8260)

    def dispatch_tick(self, gpio_high: bool) -> int:
        """Originalverteiler samt Prüfungen; nur Logging/Speicherauftrag abgefangen."""
        self.uc.mem_write(0x40001050, struct.pack("<I", int(gpio_high) << 29))
        self.call(0x82D4, 1, stubs={
            APP_BASE + 0x100B4: "logger", APP_BASE + 0xA150: "gear_save_request",
        }, gpio_output=True)
        events = [v for kind, v in self.calls if kind == "key_event"]
        if len(events) > 1:
            raise AnalysisError("Mehr als ein OEM-Ereignis je Timeraufruf.")
        return events[0] if events else 0

    def click_trace(self, count: int, *, pair_pause_ticks=0, dispatch=False) -> list[dict]:
        if type(count) is not int or not 1 <= count <= 6:
            raise AnalysisError("Demo unterstützt eine bis sechs Tastenbetätigungen.")
        if type(pair_pause_ticks) is not int or not 0 <= pair_pause_ticks <= 1000:
            raise AnalysisError("Begrenzte nichtnegative Paarpause erforderlich.")
        self.uc.mem_write(self.KEY_STATE + 0xC, b"\0" * 0xA)
        self.uc.mem_write(self.KEY_STATE + 0x1C, b"\0" * 6)
        events = []
        tick = 0
        pattern = []
        for index in range(count):
            pattern.extend(((True, 8), (False, 8)))
            if index % 2 == 1 and index < count - 1:
                pattern.append((False, pair_pause_ticks))
        for high, duration in pattern + [(False, 60)]:
            for _ in range(duration):
                tick += 1
                event = self.dispatch_tick(high) if dispatch else self.button_tick(high)
                if event:
                    row = {"tick": tick, "nominal_ms": tick * 10, "event": event}
                    if dispatch:
                        row["mode_after"] = bytes(self.uc.mem_read(self.INFO + 1, 1))[0]
                        row["mode_cycle_called"] = any(
                            kind == "original_mode_dispatch" for kind, _ in self.calls
                        )
                    events.append(row)
        return events

    def display_trace(self, values: list[int]) -> list:
        if len(values) != 21 or any(type(v) is not int or not 0 <= v <= 255 for v in values):
            raise AnalysisError("Genau 21 Anzeige-Slotwerte von 0 bis 255 erforderlich.")
        frame = bytearray(21 * 8)
        for index, value in enumerate(values):
            frame[index * 8:index * 8 + 2] = bytes((value, 1))  # Originalmodus 1: dauerhaft
        self.uc.mem_write(self.DISPLAY, bytes(frame))
        self.call(0xC6B2, stubs={
            APP_BASE + 0xC4A6: "display_command",
            APP_BASE + 0xC44A: "display_data",
            0x113DC: "pin_configuration",
        })
        return list(self.calls)

    def controller_frame(self, mode: int, upper_nibble: int) -> bytes:
        if mode not in (2, 3, 11) or upper_nibble not in (1, 2, 3):
            raise AnalysisError("Nur belegte Modus- und obere Nibblewerte zulässig.")
        self.uc.mem_write(self.INFO, b"\0" * 0x100)
        self.uc.mem_write(self.INFO, bytes((upper_nibble, mode)))
        self.uc.mem_write(self.INFO + 0x1D, b"\x01")
        self.call(0x3940, stubs={APP_BASE + 0x9300: "uart"})
        frames = [bytes.fromhex(v) for k, v in self.calls if k == "uart"]
        if len(frames) != 1:
            raise AnalysisError("Kein eindeutiger Original-UART-Frame erzeugt.")
        return frames[0]


def consume_mode_fragment(mcu: bytes, frame: bytes) -> dict:
    """Originalen ES32-Modusempfang bis vor das nächste Feld ausführen.

    Dies testet den Feldkonsumenten, nicht Framing/IRQ/gesamten UART-Parser.
    """
    from bwpatcher.ssm_firmware import ORIGINALS
    if hashlib.sha256(mcu).hexdigest() != ORIGINALS["mcu"]["sha256"]:
        raise AnalysisError("Fragment verlangt die exakte MCU-Datei 0007.")
    if len(frame) != 12 or frame[:3] != b"\x51\x10\x07" or frame[-1] != 0xAE:
        raise AnalysisError("Kein untersuchter Statusframe.")
    if sum(frame[:-2]) & 255 != frame[-2]:
        raise AnalysisError("Ungültige Statusframe-Prüfsumme.")
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
    from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC
    from unicorn import UcError

    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(0, 0xB000, 5)
    uc.mem_write(0, mcu[0x19880:0x24710])
    uc.mem_map(0x20000000, 0x10000)
    uc.mem_write(0x20001000, frame)
    uc.reg_write(UC_ARM_REG_R0, 0x20001000)
    start, end = 0x203B2 - 0x19880, 0x203D2 - 0x19880
    try:
        uc.emu_start(start | 1, end, count=100)
    except UcError as exc:
        raise AnalysisError(f"MCU-Fragmentausführung abgebrochen: {exc}") from exc
    if uc.reg_read(UC_ARM_REG_PC) != end:
        raise AnalysisError("MCU-Feldkonsument erreicht die belegte Grenze nicht.")
    upper, mode = bytes(uc.mem_read(0x20000228, 2))
    return {"upper_nibble": upper, "mode": mode}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ble", required=True, type=Path)
    parser.add_argument("--mcu", required=True, type=Path)
    args = parser.parse_args(argv)
    from bwpatcher.ssm_firmware import ORIGINALS
    try:
        ble, mcu = args.ble.read_bytes(), args.mcu.read_bytes()
        if hashlib.sha256(ble).hexdigest() != ORIGINALS["ble"]["sha256"]:
            raise AnalysisError("Nicht das exakt untersuchte BLE-Original.")
        app = inspect_ble(ble).app
        emu = OriginalAppEmulator(app)
        clicks = {str(n): emu.click_trace(n) for n in (1, 2, 5, 6)}
        paired = emu.click_trace(6, pair_pause_ticks=60)
        emu.uc.mem_write(emu.INFO + 1, b"\x03")
        emu.uc.mem_write(emu.INFO + 0xE, b"\x01")
        dispatched = emu.click_trace(6, pair_pause_ticks=60, dispatch=True)
        light = []
        for _ in range(2):
            single = emu.click_trace(1, dispatch=True)
            light.append({"trace": single, "gpio_output": struct.unpack(
                "<I", bytes(emu.uc.mem_read(0x40001000, 4))
            )[0]})
        gate = OriginalAppEmulator(app)
        gate.uc.mem_write(gate.INFO + 1, b"\x03")
        gate.uc.mem_write(gate.INFO + 0xE, b"\x01")
        gate.uc.mem_write(gate.INFO + 0x10, b"\x01")
        gated = gate.click_trace(6, pair_pause_ticks=60, dispatch=True)
        display = {}
        for mask in (1, 2, 4, 7):
            values = [0] * 21
            values[12] = mask
            display[str(mask)] = emu.display_trace(values)
        uart = []
        for mode in (11, 2, 3):
            frame = emu.controller_frame(mode, 2)
            uart.append({"frame": frame.hex(), "mcu_consumer": consume_mode_fragment(mcu, frame)})
    except ImportError as exc:
        parser.exit(1, f"Forschungsabhängigkeit fehlt: {exc}. poetry install --with research\n")
    except (OSError, AnalysisError) as exc:
        parser.exit(1, f"Analyse abgebrochen: {exc}\n")
    print(json.dumps({
        "status": "Originalroutinen mit emulierter Peripherie, kein Hardwaretest",
        "ssm_patch_available": False, "clicks": clicks,
        "paired_doubles_60_extra_low_ticks": paired,
        "original_dispatcher_paired_doubles": dispatched,
        "original_single_light": light, "original_mode_gate": gated,
        "dispatcher_stubs": ["logger", "gear_save_request"],
        "display": display, "uart": uart,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
