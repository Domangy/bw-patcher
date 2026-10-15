#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Originale Speicher-, Kontext-, Begrenzungs- und Rückkanalnachweise, nur offline.

Kein Linker, keine Codeinjektion, kein Firmwareexport. Fremde Images werden
abgewiesen. Peripherie, gesamter Boot und reale Controllerantworten sind ungetestet.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

from bwpatcher.mi5pro_research import APP_BASE, APP_SHA256, AnalysisError, inspect_ble
from bwpatcher.mi5pro_emulator import OriginalAppEmulator
from bwpatcher.ssm_firmware import ORIGINALS

MCU_BASE = 0x19880
MCU_END = 0x24710
MCU_RAM = 0x20000000
MCU_STACK = 0x20001BA8
SENTINEL = 0x10000000


def require_original(data: bytes, component: str):
    expected = ORIGINALS[component]
    if len(data) != expected['size'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
        raise AnalysisError(f'Exaktes untersuchtes {component}-Original erforderlich.')


def ble_memory_layout(app: bytes) -> dict:
    if hashlib.sha256(app).hexdigest() != APP_SHA256:
        raise AnalysisError('Speicherzuordnung verlangt das exakt untersuchte APP.')
    def word(offset):
        return struct.unpack_from('<I', app, offset)[0]
    copies = []
    for dst, src, size in ((0x6E4, 0x6E0, 0x6DC), (0x6F0, 0x6EC, 0x6E8)):
        region = {'destination': word(dst), 'source_address': word(src), 'size': word(size)}
        offset = region['source_address'] - APP_BASE
        if not 0 <= offset < offset + region['size'] <= len(app):
            raise AnalysisError('Initialisierungsquelle liegt ausserhalb des APP.')
        region['source_app_offset'] = offset
        region['end'] = region['destination'] + region['size']
        copies.append(region)
    zero = {'destination': word(0x6F8), 'size': word(0x6F4)}
    zero['end'] = zero['destination'] + zero['size']
    return {
        'initializer_app_offset': 0x4DC,
        'rom_operations_modelled_not_executed': [0x59E9A, 0x5A01C],
        'copies': copies, 'zero': zero,
        'zero_length_sections_at': word(0x704),
        'synthetic_emulator_stack': 0x20FFF0,
        'private_ram_reserved': False, 'executable_extension_reserved': False,
        'note': 'Abschnittsgrenzen sind keine freien Heap-/Taskstackgrenzen.',
    }


class McuOriginal:
    """Identifizierter ES32-Code, tatsächlicher Vektor-SP, keine MMIO-Abbildung."""
    def __init__(self, image: bytes):
        require_original(image, 'mcu')
        from unicorn import (
            Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE,
            UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ,
        )
        from unicorn.arm_const import (
            UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
            UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
            UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
            UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
        )
        self.regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                     UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                     UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)
        self.sp, self.lr, self.pc = UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
        self.image = image
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.uc.mem_map(0, 0xB000, 5)
        self.uc.mem_write(0, image[MCU_BASE:MCU_END])
        self.uc.mem_map(MCU_RAM, 0x10000)
        self.uc.mem_map(SENTINEL, 0x1000)
        self.failure = None
        self.min_sp = MCU_STACK
        self.writes = []
        self.uc.hook_add(UC_HOOK_CODE, self._instruction)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self._write)
        self.uc.hook_add(UC_HOOK_MEM_READ, self._read)
        for i, reg in enumerate(self.regs[4:]):
            self.uc.reg_write(reg, 0xB4C50000 + i * 0x101)
        # Originaler Scatterloader: kein angenommener Klartext-Datenbereich.
        scatter = [struct.unpack_from('<IIII', image, off) for off in (0x24394, 0x243A4)]
        if scatter != [(0xAB34, MCU_RAM, 0x838, 0x9CC),
                       (0xAE90, MCU_RAM + 0x838, 0x1370, 0x83D4)]:
            raise AnalysisError('Unbekannte MCU-Initialisierungstabelle.')
        self.scatter = scatter
        for source, destination, size, function in scatter:
            self.call(MCU_BASE + function, source, destination, size)
        self.initial_limits = list(struct.unpack('<14H', self.read(0x2000080C, 28)))

    def read(self, address, size):
        if not MCU_RAM <= address <= address + size <= MCU_STACK or size < 0:
            raise AnalysisError('MCU-RAM-Bereich ausserhalb des untersuchten statischen Bereichs.')
        return bytes(self.uc.mem_read(address, size))

    def seed(self, address, data):
        self.read(address, len(data))
        self.uc.mem_write(address, data)

    def _instruction(self, uc, address, size, _):
        self.min_sp = min(self.min_sp, uc.reg_read(self.sp))
        if address == SENTINEL:
            uc.emu_stop()
        elif not 0 <= address < MCU_END - MCU_BASE:
            self.failure = f'Nicht modellierter MCU-Codeaufruf {address:#x}.'
            uc.emu_stop()

    def _write(self, uc, access, address, size, value, _):
        self.writes.append((address, size, value))
        if not MCU_RAM <= address < address + size <= MCU_STACK:
            self.failure = f'Unzulässiger MCU-Schreibzugriff {address:#x}.'
            uc.emu_stop()

    def _read(self, uc, access, address, size, value, _):
        if not (
            0 <= address < address + size <= MCU_END - MCU_BASE
            or MCU_RAM <= address < address + size <= MCU_STACK
        ):
            self.failure = f'Unmodellierter MCU-Lesezugriff {address:#x}.'
            uc.emu_stop()

    def call(self, file_offset, *args, end=None, r4=None):
        from unicorn import UcError
        if not MCU_BASE <= file_offset < MCU_END or file_offset % 2:
            raise AnalysisError('Ungültiger MCU-Einstieg.')
        if end is not None and (not MCU_BASE <= end < MCU_END or end % 2):
            raise AnalysisError('Ungültige MCU-Fragmentgrenze.')
        self.failure = None
        self.writes.clear()
        self.min_sp = MCU_STACK
        self.uc.reg_write(self.sp, MCU_STACK)
        self.uc.reg_write(self.lr, SENTINEL | 1)
        for reg, value in zip(self.regs[:4], (*args, 0, 0, 0, 0)):
            self.uc.reg_write(reg, value)
        if r4 is not None:
            self.uc.reg_write(self.regs[4], r4)
        saved = [self.uc.reg_read(reg) for reg in self.regs[4:]]
        target = end - MCU_BASE if end is not None else SENTINEL
        try:
            self.uc.emu_start((file_offset - MCU_BASE) | 1,
                              target if end is not None else 0, count=100000)
        except UcError as exc:
            raise AnalysisError(f'MCU-Originalausführung abgebrochen: {exc}') from exc
        if self.failure or self.uc.reg_read(self.pc) != target:
            raise AnalysisError(self.failure or 'MCU-Original erreicht seine Grenze nicht.')
        if end is None and (
            self.uc.reg_read(self.sp) != MCU_STACK
            or saved != [self.uc.reg_read(reg) for reg in self.regs[4:]]
        ):
            raise AnalysisError('MCU-Original verletzt den geprüften Register-/Stackvertrag.')

    def select_limits(self, prefix: bytes) -> dict:
        if len(prefix) != 5 or not prefix.isdigit():
            raise AnalysisError('Genau fünf ASCII-Ziffern als synthetischer SN-Präfix erforderlich.')
        self.seed(0x20001800, prefix)
        self.call(0x1DEA4, 0x20001800, 0x20000324, 0x20000326)
        drive, sport = struct.unpack('<HH', self.read(0x20000324, 4))
        return {'prefix': prefix.decode(), 'drive_raw': drive, 'sport_raw': sport,
                'index': self.read(0x200003CA, 1)[0]}

    def consume_mode(self, frame: bytes):
        if len(frame) != 12 or frame[:3] != b'\x51\x10\x07' or frame[-1] != 0xAE:
            raise AnalysisError('Kein untersuchter BLE-Modusframe.')
        if sum(frame[:-2]) & 255 != frame[-2]:
            raise AnalysisError('Ungültige BLE-Modusframe-Prüfsumme.')
        self.seed(0x20001800, frame)
        self.call(0x203B2, 0x20001800, end=0x203D2)

    def speed_selection(self, mode: int, *, override_flag=0) -> int:
        if type(mode) is not int or not 0 <= mode <= 15 or override_flag not in (0, 1):
            raise AnalysisError('Ungültiger synthetischer Modus/Originalflag.')
        self.seed(0x20000229, bytes((mode,)))
        self.seed(0x20000339, bytes((override_flag,)))
        self.call(0x1D0C6, 0, end=0x1D0F2, r4=0x20001768)
        return struct.unpack('<H', self.read(0x2000177C, 2))[0]

    def status_frame(self) -> bytes | None:
        before = self.read(0x200002C9, 1)[0]
        if before >= 8:
            raise AnalysisError('Unzulässiger Original-Senderingindex.')
        self.call(0x211F8)
        if self.read(0x200002C9, 1)[0] == before:
            return None  # Originale Session-/Zeit-/Zustandsgates bleiben wirksam.
        address = 0x200010B5 + 150 * before
        length = self.read(address, 1)[0]
        if not 0 < length < 150:
            raise AnalysisError('Originaler Statusbuilder liefert keine begrenzte Ringnachricht.')
        return self.read(address + 1, length)


def decode_status(frame: bytes) -> dict:
    """Strikter Beobachter für 61/30; keine Bestätigung einer angewendeten Begrenzung."""
    if len(frame) != 15 or frame[:3] != b'\x61\x30\x0a' or frame[-1] != 0x9E:
        raise AnalysisError('Kein vollständiger bekannter 61/30-Statusframe.')
    if sum(frame[:-2]) & 255 != frame[-2]:
        raise AnalysisError('Ungültige Controller-Statusprüfsumme.')
    mode, upper = frame[3] & 15, frame[3] >> 4
    if mode not in (2, 3, 11) or upper not in (1, 2, 3):
        raise AnalysisError('Unbekannter Original-Moduszustand im Statusframe.')
    return {'echoed_mode': mode, 'upper_nibble': upper,
            'speed_raw': int.from_bytes(frame[9:11], 'big'),
            'confirms_applied_speed_limit': False,
            'wire_sequence_number_present': False}


class BleIntegration(OriginalAppEmulator):
    """Zusätzliche Beobachtungspunkte, keine Änderung einer Originalinstruktion."""
    WATCH = {0x8264, 0x8268, 0x82FC, 0x8300, 0x8550, 0x8554,
             0x611C, 0x6120, 0xC76C, 0xC770, 0x43C4, 0x4320}

    def __init__(self, app, *, volatile_stubs=False):
        super().__init__(app)
        from unicorn.arm_const import (
            UC_ARM_REG_R3, UC_ARM_REG_R12, UC_ARM_REG_CPSR,
        )
        self.r3, self.r12, self.cpsr = UC_ARM_REG_R3, UC_ARM_REG_R12, UC_ARM_REG_CPSR
        self.volatile_stubs = volatile_stubs
        self.snapshots = []
        self.minimum_sp = 0x20FFF0
        self.layout = ble_memory_layout(app)
        self.uc.mem_map(0x5A000, 0x1000, 5)  # Nur Rückkehrmodell des bekannten ROM-Helpers.
        for region in self.layout['copies']:
            offset, size = region['source_app_offset'], region['size']
            self.uc.mem_write(region['destination'], app[offset:offset + size])
        zero = self.layout['zero']
        self.uc.mem_write(zero['destination'], b'\0' * zero['size'])

    def _instruction(self, uc, address, size, extra):
        self.minimum_sp = min(self.minimum_sp, uc.reg_read(self.sp))
        if address - APP_BASE in self.WATCH:
            flags = uc.reg_read(self.cpsr)
            self.snapshots.append({
                'app_offset': address - APP_BASE,
                'sp': uc.reg_read(self.sp), 'lr': uc.reg_read(self.lr),
                'r0': uc.reg_read(self.r0), 'r1': uc.reg_read(self.r1),
                'r2': uc.reg_read(self.r2), 'r3': uc.reg_read(self.r3),
                'r12': uc.reg_read(self.r12),
                **{f'r{i + 4}': uc.reg_read(r) for i, r in enumerate(self.saved_registers)},
                'apsr': flags & 0xF80F0000,
                'itstate': ((flags >> 25) & 3) | ((flags >> 8) & 0xFC),
            })
        is_stub = address in self.stubs
        super()._instruction(uc, address, size, extra)
        if is_stub and self.volatile_stubs and not self.failure:
            for index, reg in enumerate((self.r1, self.r2, self.r3, self.r12)):
                uc.reg_write(reg, 0xCCDD0000 + index)
            uc.reg_write(self.cpsr, (uc.reg_read(self.cpsr) & ~0xF8000000) | 0xA8000000)

    def call(self, *args, **kwargs):
        self.snapshots.clear()
        self.minimum_sp = 0x20FFF0
        return super().call(*args, **kwargs)

    def receive_raw(self, frame: bytes) -> dict:
        # Absichtlich originalgetreu; der strikte Adapter muss decode_status vorschalten.
        if not isinstance(frame, (bytes, bytearray)) or not 1 <= len(frame) <= 150:
            raise AnalysisError('Begrenzter Frame für den emulierten Originalempfänger erforderlich.')
        frame = bytes(frame)
        self.uc.mem_write(0x20869F, frame + b'\0' * (150 - len(frame)))
        self.uc.mem_write(0x20869D, bytes((len(frame),)))
        self.uc.mem_write(0x20856C, b'\x01\0')
        self.call(0x4476, 0x20856A, stubs={0x5A01C: 'rom_rx_clear_not_executed'})
        return {
            'status_30_dispatched': any(s['app_offset'] == 0x43C4 for s in self.snapshots),
            'rom_rx_clear_stub_used': any(
                kind == 'rom_rx_clear_not_executed' for kind, _ in self.calls
            ),
            'requested_mode': bytes(self.uc.mem_read(self.INFO + 1, 1))[0],
            'feedback_mode': bytes(self.uc.mem_read(0x2082D1, 1))[0],
            'feedback_upper': bytes(self.uc.mem_read(0x2082D0, 1))[0],
            'feedback_speed_raw_or_adjusted': struct.unpack(
                '<H', bytes(self.uc.mem_read(0x2082CE, 2))
            )[0],
        }


def integration_report(ble: bytes, mcu: bytes) -> dict:
    require_original(ble, 'ble')
    app = inspect_ble(ble).app
    layout = ble_memory_layout(app)
    machine = McuOriginal(mcu)
    prefixes = [mcu[o:o + 5] for o in range(0x24164, 0x24187, 5)]
    regions = [machine.select_limits(p) for p in prefixes]
    sender = OriginalAppEmulator(app)
    receiver = BleIntegration(app)
    receiver.uc.mem_write(receiver.INFO + 1, b'\x02')
    machine = McuOriginal(mcu)
    machine.consume_mode(sender.controller_frame(3, 2))
    frame = machine.status_frame()
    if frame is None:
        raise AnalysisError('Originalstatus wurde im initialisierten Testzustand nicht erzeugt.')
    feedback = {'frame': frame.hex(), 'strict_decode': decode_status(frame),
                'original_receiver': receiver.receive_raw(frame)}
    feedback_stack = machine.min_sp
    ambiguity = []
    for prefix in (b'60556', b'60564'):
        variant = McuOriginal(mcu)
        selected = variant.select_limits(prefix)
        variant.consume_mode(sender.controller_frame(3, 2))
        ambiguity.append({**selected, 'status_frame': variant.status_frame().hex()})
    short_frame = bytes.fromhex('613000919e')
    short_result = BleIntegration(app).receive_raw(short_frame)
    try:
        decode_status(short_frame)
    except AnalysisError:
        strict_rejected_short = True
    else:
        strict_rejected_short = False
    # Der Vergleichspfad bleibt vollständig unverändert.
    speed = []
    for prefix in prefixes:
        limits = machine.select_limits(prefix)
        for mode in (11, 2, 3):
            speed.append({**limits, 'mode': mode, 'selected_raw': machine.speed_selection(mode)})
    observer = BleIntegration(app, volatile_stubs=True)
    observer.uc.mem_write(observer.INFO + 1, b'\x03')
    observer.uc.mem_write(observer.INFO + 0xE, b'\x01')
    for level in [True] * 8 + [False] * 8 + [True] * 8 + [False]:
        observer.dispatch_tick(level)
    contexts = list(observer.snapshots)
    stack = observer.minimum_sp
    observer.uc.mem_write(0x208660, b'\x04')
    observer.call(0x60F4)
    contexts.extend(observer.snapshots)
    stack = min(stack, observer.minimum_sp)
    values = [0] * 21
    values[12] = 4
    observer.display_trace(values)
    contexts.extend(observer.snapshots)
    return {
        'status': 'Nur Originalcode-Nachweise; kein integrierter SSM-Patch',
        'originals': {k: v['sha256'] for k, v in ORIGINALS.items()},
        'ble_memory': layout,
        'mcu_scatter_entries': [list(row) for row in machine.scatter],
        'mcu_initial_limit_table': machine.initial_limits,
        'prefix_limit_selection': regions, 'original_speed_selection': speed,
        'controller_feedback': feedback,
        'mcu_status_function_minimum_stack': feedback_stack,
        'different_limits_identical_mode_status': ambiguity,
        'original_short_frame_dispatch': short_result,
        'strict_observer_rejects_short_frame': strict_rejected_short,
        'hook_contexts': contexts,
        'synthetic_stack_minimum_in_selected_calls': min(stack, observer.minimum_sp),
        'volatile_stub_registers_clobbered': ['r1', 'r2', 'r3', 'r12', 'APSR'],
        'ssm_patch_available': False, 'hardware_validated': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ble', required=True, type=Path)
    parser.add_argument('--mcu', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = integration_report(args.ble.read_bytes(), args.mcu.read_bytes())
    except (OSError, AnalysisError, ImportError) as exc:
        parser.exit(1, f'Originalanalyse abgebrochen: {exc}\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
