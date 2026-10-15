#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Fortsetzung: Bremse, vollständige Grenz-/Reglerfunktion und Kontextgrenzen.

Nur Offline-Nachweise mit unverändertem Originalcode. Kein SSM-Adapter, keine
Freigabe aus Bremswerten, keine Firmwareausgabe und keine Hardwareverbindung.
"""

import argparse
import json
from pathlib import Path
import struct

from bwpatcher.mi5pro_integration import (
    BleIntegration, McuOriginal, MCU_BASE, decode_status, require_original,
)
from bwpatcher.mi5pro_research import APP_BASE, AnalysisError, inspect_ble


def bounded_integer(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise AnalysisError('Begrenzter nichtnegativer ganzzahliger Testwert erforderlich.')
    return value


class BleConstraints(BleIntegration):
    """Beobachtet externe Auftragsargumente; deren Körper bleiben ungetestet."""
    def __init__(self, app):
        super().__init__(app)
        self.external_arguments = []
        self.uc.mem_map(0x26000, 0x1000, 5)  # Nur der explizite Taskauftrag-Stub, kein ROM-Code.

    def _instruction(self, uc, address, size, extra):
        if address in self.stubs and self.stubs[address] in (
            'task_create_not_executed', 'line_test_response_not_executed',
        ):
            kind = self.stubs[address]
            row = {'kind': kind, 'address': address,
                   **{f'r{i}': uc.reg_read(r) for i, r in enumerate(
                       (self.r0, self.r1, self.r2, self.r3))}}
            if kind == 'task_create_not_executed':
                row['stack_arguments'] = list(struct.unpack(
                    '<II', bytes(uc.mem_read(uc.reg_read(self.sp), 8))))
            else:
                if row['r2'] != 2:
                    raise AnalysisError('Unerwartete Bremsdiagnose-Länge.')
                row['payload'] = bytes(uc.mem_read(row['r1'], 2)).hex()
            self.external_arguments.append(row)
        super()._instruction(uc, address, size, extra)

    def brake_fields(self, throttle_raw, brake_raw, *, powered=True, info_2c=0, ready=True):
        for value in (throttle_raw, brake_raw):
            bounded_integer(value, 4095)  # Begrenzter ADC-Testbereich, keine physische Kalibrierung.
        bounded_integer(info_2c, 255)  # Bedeutung dieses Unterdrückungsbytes nicht vollständig geklärt.
        if type(powered) is not bool or type(ready) is not bool:
            raise AnalysisError('Explizite synthetische Betriebs-/Bereitschaftsflags erforderlich.')
        self.uc.mem_write(self.INFO, b'\0' * 0x50)
        self.uc.mem_write(self.INFO, b'\x02\x03')
        self.uc.mem_write(self.INFO + 0x1D, bytes((int(powered),)))
        self.uc.mem_write(self.INFO + 0x2C, bytes((info_2c,)))
        self.uc.mem_write(0x2085C0, struct.pack('<HH', throttle_raw, brake_raw))
        self.uc.mem_write(0x2085CC, bytes((int(ready),)))
        self.call(0x75FA)
        values = bytes(self.uc.mem_read(self.INFO + 0x15, 2))
        self.call(0x3940, stubs={APP_BASE + 0x9300: 'uart'})
        frames = [bytes.fromhex(v) for k, v in self.calls if k == 'uart']
        if len(frames) != 1:
            raise AnalysisError('Kein eindeutiger Originalframe nach Analogverarbeitung.')
        return {'throttle_raw': throttle_raw, 'brake_raw': brake_raw,
                'throttle_percent': values[0], 'brake_percent': values[1],
                'adc_ready': ready, 'frame': frames[0].hex(),
                'fresh_sample_proven': False, 'activation_intent_proven': False}

    def brake_diagnostic(self, raw):
        bounded_integer(raw, 4095)
        self.uc.mem_write(0x2085C2, struct.pack('<H', raw))
        self.external_arguments.clear()
        self.call(0x684A, stubs={APP_BASE + 0x100B4: 'logger',
                              APP_BASE + 0x6328: 'line_test_response_not_executed'})
        return self.external_arguments[-1]

    def task_creation(self):
        self.external_arguments.clear()
        self.call(0x2546, stubs={0x269D0: 'task_create_not_executed'})
        return self.external_arguments[-1]

    def brake_fault_path(self, raw):
        initial = self.brake_fields(600, raw)
        for _ in range(400):
            self.call(0x7922)
        state_400 = bytes(self.uc.mem_read(self.INFO + 0x18, 1))[0]
        self.call(0x7922)
        state_401 = bytes(self.uc.mem_read(self.INFO + 0x18, 1))[0]
        self.call(0x6FE8, stubs={APP_BASE + 0x100B4: 'logger'})
        code = bytes(self.uc.mem_read(self.INFO + 0x2C, 1))[0]
        self.call(0x75FA)
        return {'raw': raw, 'initial_brake_percent': initial['brake_percent'],
                'analog_state_after_400_calls': state_400,
                'analog_state_after_401_calls': state_401,
                'aggregated_info_2c': code,
                'final_brake_percent': bytes(self.uc.mem_read(self.INFO + 0x16, 1))[0],
                'wall_clock_duration_proven': False}

    def doubles_with_brake(self, raw):
        self.brake_fields(600, raw)
        self.uc.mem_write(self.INFO + 0xE, b'\x01')
        return self.click_trace(6, pair_pause_ticks=60, dispatch=True)

    def reserved_reset_selection(self, throttle, brake, *, speed=0, locked=False):
        self.brake_fields(throttle, brake)
        bounded_integer(speed, 65535)
        if type(locked) is not bool:
            raise AnalysisError('Explizites synthetisches Sperrflag erforderlich.')
        self.uc.mem_write(0x2082CE, struct.pack('<H', speed))
        self.uc.mem_write(self.INFO + 0x10, bytes((int(locked),)))
        self.call(0xB6A2, stubs={APP_BASE + 0xB492: 'oem_reset_not_executed',
                               APP_BASE + 0x100B4: 'logger'})
        return any(k == 'oem_reset_not_executed' for k, _ in self.calls)


class McuConstraints(McuOriginal):
    """Lese-/Ausführungsspuren statt erfundener Verbindung zwischen Regelblöcken."""
    def __init__(self, image):
        self.reads = []
        self.executed = []
        self.boundary_access = None
        super().__init__(image)
        from unicorn import UC_HOOK_MEM_UNMAPPED
        self.uc.hook_add(UC_HOOK_MEM_UNMAPPED, self._unmapped)

    def _unmapped(self, uc, access, address, size, value, extra):
        self.boundary_access = {'access': access, 'address': address, 'size': size,
                                'pc_file_offset': uc.reg_read(self.pc) + MCU_BASE}
        return False  # Kein MMIO-Ersatzwert und keine automatische Fortsetzung.

    def _read(self, uc, access, address, size, value, extra):
        self.reads.append((uc.reg_read(self.pc) + MCU_BASE, address, size))
        super()._read(uc, access, address, size, value, extra)

    def _instruction(self, uc, address, size, extra):
        self.executed.append(address + MCU_BASE)
        super()._instruction(uc, address, size, extra)

    def call(self, *args, **kwargs):
        self.reads.clear()
        self.executed.clear()
        return super().call(*args, **kwargs)

    def consume_analog_fragment(self, frame):
        # Der alte Modusfragment-Validator prüft vollständige Form und Summe vor.
        self.consume_mode(frame)
        self.call(0x203B2, 0x20001800, end=0x20502, r4=0)
        return {'throttle_percent': self.read(0x20000233, 1)[0],
                'brake_percent': self.read(0x20000234, 1)[0]}

    def control_step(self):
        self.call(0x1D078)
        def u(address, size=4):
            return int.from_bytes(self.read(address, size), 'little')
        return {'selected_limit_raw': u(0x2000177C, 2),
                'controller_setpoint_raw': u(0x200003F2, 2),
                'control_output_raw': u(0x20001780),
                'control_output_mirror_raw': u(0x2000042C),
                'reported_speed_raw': u(0x20000236, 2),
                'setpoint_read_by_control': any(
                    pc == 0x1D1E4 and addr == 0x200003F2 for pc, addr, _ in self.reads),
                'original_clamp_executed': 0x1D0EC in self.executed,
                'minimum_sp': self.min_sp,
                'motor_effect_proven': False}

    def brake_control_step(self):
        self.call(0x1C234)
        return {'brake_scaled': int.from_bytes(self.read(0x2000041C, 4), 'little'),
                'brake_active_262': self.read(0x20000262, 1)[0],
                'brake_active_263': self.read(0x20000263, 1)[0],
                'physical_braking_proven': False}

    def peripheral_boundary(self, entry):
        if entry not in (0x1B67C, 0x1A938):
            raise AnalysisError('Nur die zwei untersuchten Motorpfade sind für diesen Grenztest erlaubt.')
        self.boundary_access = None
        try:
            self.call(entry)
        except AnalysisError:
            if self.boundary_access is None:
                raise
            return {'entry_file_offset': entry, 'blocked': True,
                    'unmapped': self.boundary_access, 'peripheral_model_supplied': False}
        return {'entry_file_offset': entry, 'blocked': False,
                'peripheral_model_supplied': False, 'whole_function_coverage_proven': False}


def reference_candidates(app, targets):
    """Konservative Halbwortsuche; kein CFG und kein Beweis fehlender Referenzen."""
    # Hashprüfung vor Capstone und vor jeder Adressauswertung.
    from bwpatcher.mi5pro_integration import ble_memory_layout
    ble_memory_layout(app)
    import capstone as cs
    engine = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_THUMB)
    engine.detail = True
    results = []
    for offset in range(0x400, len(app) - 3, 2):
        instruction = next(engine.disasm(app[offset:offset + 4], APP_BASE + offset, 1), None)
        if (instruction and instruction.mnemonic.startswith('b') and instruction.operands
                and instruction.operands[0].type == cs.arm.ARM_OP_IMM
                and instruction.operands[0].imm - APP_BASE in targets):
            results.append({'source_app_offset': offset,
                            'target_app_offset': instruction.operands[0].imm - APP_BASE,
                            'kind': 'direct_branch_candidate'})
    for offset in range(0x400, len(app) - 3, 4):
        value = struct.unpack_from('<I', app, offset)[0]
        if value & 1 and (value & ~1) - APP_BASE in targets:
            results.append({'source_app_offset': offset,
                            'target_app_offset': (value & ~1) - APP_BASE,
                            'kind': 'aligned_thumb_pointer_candidate'})
    return {'complete_control_flow_proven': False, 'candidates': results}


def constraints_report(ble, mcu):
    require_original(ble, 'ble')
    require_original(mcu, 'mcu')
    app = inspect_ble(ble).app
    analog = []
    for raw in (600, 900, 901, 916, 1400, 2449, 3000):
        row = BleConstraints(app).brake_fields(600, raw)
        row['mcu_consumer'] = McuConstraints(mcu).consume_analog_fragment(bytes.fromhex(row['frame']))
        analog.append(row)
    steps = []
    machine = McuConstraints(mcu)
    machine.select_limits(b'60556')
    machine.seed(0x20000229, b'\x03')
    machine.seed(0x20001760, struct.pack('<I', 5000))
    machine.seed(0x20000224, struct.pack('<I', 5000))
    for _ in range(2):
        steps.append(machine.control_step())
    # Keine neue Grenze: originaler Drive-/Sportwechsel unter dem Originalvergleich.
    machine.seed(0x20000333, b'\x01')
    machine.seed(0x20000229, b'\x02')
    slow = machine.control_step()
    machine.seed(0x20000229, b'\x03')
    fast = machine.control_step()
    alternate = McuConstraints(mcu)
    alternate.select_limits(b'60556')
    alternate.seed(0x20000229, b'\x03')
    alternate.seed(0x200003F2, struct.pack('<H', 200))
    alternate.seed(0x20000320, b'\x03')
    alternate.seed(0x20000333, b'\x01')
    setpoint_different = alternate.control_step()
    alternate.seed(0x20000228, b'\x02')
    first = alternate.status_frame()
    baseline = McuConstraints(mcu)
    baseline.select_limits(b'60556')
    baseline.seed(0x20000229, b'\x03')
    normal = baseline.control_step()
    baseline.seed(0x20000228, b'\x02')
    second = baseline.status_frame()
    boundaries = []
    for entry in (0x1B67C, 0x1A938):
        probe = McuConstraints(mcu)
        probe.select_limits(b'60556')
        probe.seed(0x20000229, b'\x03')
        probe.control_step()
        probe.control_step()
        boundaries.append(probe.peripheral_boundary(entry))
    return {
        'schema_version': 1, 'base_commit': 'f940ba7',
        'brake_diagnostic': BleConstraints(app).brake_diagnostic(1400),
        'original_brake_fault_path': BleConstraints(app).brake_fault_path(4095),
        'analog_path': analog,
        'oem_doubles_brake_held': BleConstraints(app).doubles_with_brake(1400),
        'brake_only_proves_intent': False,
        'reserved_reset_selection': [
            {'throttle_raw': t, 'brake_raw': b,
             'oem_reset_call_selected': BleConstraints(app).reserved_reset_selection(t, b)}
            for t, b in ((600, 1600), (1600, 600), (1400, 1600), (1600, 1400), (1600, 1600))
        ],
        'control_steps': steps,
        'normal_drive_to_sport': [slow, fast],
        'same_mode_different_setpoint': [setpoint_different, normal],
        'status_for_different_setpoints': [first.hex(), second.hex()],
        'status_has_applied_limit_ack': decode_status(first)['confirms_applied_speed_limit'],
        'app_task_creation_arguments': BleConstraints(app).task_creation(),
        'peripheral_boundary_scenario': 'Originaldaten, Präfix 60556, Sport, zwei isolierte Regleraufrufe',
        'peripheral_boundaries': boundaries,
        'inbound_reference_candidates': reference_candidates(
            app, {0x8264, 0x82FC, 0x8550, 0x611C, 0xC76C, 0x82D4, 0x60F4, 0xC6B2, 0x9E18}),
        'new_speed_state_implemented': False,
        'ssm_hooks_injected': False, 'hardware_tests': 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ble', required=True, type=Path)
    parser.add_argument('--mcu', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = constraints_report(args.ble.read_bytes(), args.mcu.read_bytes())
    except (OSError, AnalysisError, ImportError) as exc:
        parser.exit(1, f'Originalanalyse abgebrochen: {exc}\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
