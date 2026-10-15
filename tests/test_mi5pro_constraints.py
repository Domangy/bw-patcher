#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Neue Grenzen ab f940ba7; kein Motor-/NVM-/Flashzugriff."""

from dataclasses import dataclass
import os
from pathlib import Path
import struct

import pytest

from bwpatcher.mi5pro_constraints import (
    BleConstraints, McuConstraints, bounded_integer, constraints_report, reference_candidates,
)
from bwpatcher.mi5pro_research import APP_BASE, AnalysisError, inspect_ble


@pytest.mark.parametrize('value', [0, 1, 4095])
def test_bounded_probe_input_accepts_only_adc_test_domain(value):
    assert bounded_integer(value, 4095) == value


@pytest.mark.parametrize('value', [-1, True, False, 4096, 65535, 1.5, None, '600'])
def test_bounded_probe_input_rejects_ambiguous_values(value):
    with pytest.raises(AnalysisError):
        bounded_integer(value, 4095)


@pytest.mark.parametrize('factory', [BleConstraints, McuConstraints,
                                    lambda data: reference_candidates(data, {0x8550})])
def test_constraint_tools_reject_unidentified_originals(factory):
    with pytest.raises(AnalysisError):
        factory(b'kein Original')


@dataclass(repr=False)
class OriginalFiles:
    ble: bytes
    mcu: bytes
    app: bytes


@pytest.fixture(scope='module')
def originals():
    directory = os.environ.get('MI5PRO_FIRMWARE_DIR')
    if not directory:
        pytest.skip('Lokale Originale erforderlich; kein Firmwarefixture im Repository.')
    pytest.importorskip('unicorn')
    base = Path(directory)
    ble = (base / 'ble_2.7.0_0015.bin').read_bytes()
    return OriginalFiles(ble, (base / 'mcu_0007.bin').read_bytes(), inspect_ble(ble).app)


@pytest.mark.parametrize('raw,expected', [(600, 0), (900, 0), (901, 0), (916, 1),
                                          (1400, 32), (2449, 99), (3000, 100)])
def test_original_brake_chain_from_diagnostic_and_scaler_to_wire_and_mcu(originals, raw, expected):
    ble = BleConstraints(originals.app)
    diagnostic = ble.brake_diagnostic(raw)
    assert diagnostic['r0'] == 0xe9 and diagnostic['payload'] == raw.to_bytes(2, 'big').hex()
    row = ble.brake_fields(600, raw)
    assert row['brake_percent'] == expected and row['throttle_percent'] == 0
    assert not row['fresh_sample_proven'] and not row['activation_intent_proven']
    frame = bytes.fromhex(row['frame'])
    assert frame[6] == 0 and frame[7] == expected
    assert sum(frame[:-2]) & 255 == frame[-2]
    assert McuConstraints(originals.mcu).consume_analog_fragment(frame) == {
        'throttle_percent': 0, 'brake_percent': expected,
    }


def test_normalized_zero_is_not_a_proof_of_released_brake(originals):
    ble = BleConstraints(originals.app)
    normal = ble.brake_fields(600, 1400)
    suppressed = ble.brake_fields(600, 1400, info_2c=0x15)
    assert normal['brake_percent'] == 32 and suppressed['brake_percent'] == 0
    assert suppressed['brake_raw'] == normal['brake_raw']
    assert not suppressed['activation_intent_proven']


def test_adc_ready_flag_does_not_make_the_original_scaler_check_freshness(originals):
    ble = BleConstraints(originals.app)
    assert ble.brake_fields(600, 1400, ready=False)['brake_percent'] == 32
    assert ble.brake_fields(600, 1400, powered=False)['brake_percent'] == 0


@pytest.mark.parametrize('raw,fault', [(0, True), (100, True), (101, False),
                                     (3199, False), (3200, True), (4095, True)])
def test_original_brake_fault_detection_aggregation_and_suppression_chain(originals, raw, fault):
    result = BleConstraints(originals.app).brake_fault_path(raw)
    assert result['analog_state_after_400_calls'] == 0
    assert result['analog_state_after_401_calls'] == (6 if fault else 0)
    assert result['aggregated_info_2c'] == (0x15 if fault else 0)
    if fault:
        assert result['final_brake_percent'] == 0
    else:
        assert result['initial_brake_percent'] == result['final_brake_percent']
    assert not result['wall_clock_duration_proven']


@pytest.mark.parametrize('brake', [600, 1400, 1600])
def test_original_double_actions_are_unchanged_while_brake_sample_differs(originals, brake):
    rows = BleConstraints(originals.app).doubles_with_brake(brake)
    assert [row['event'] for row in rows] == [2, 2, 2]
    assert [row['mode_after'] for row in rows] == [11, 2, 3]
    assert all(row['mode_cycle_called'] for row in rows)


@pytest.mark.parametrize('throttle,brake,speed,locked,selected', [
    (600, 1600, 0, False, False), (1600, 600, 0, False, False),
    (1400, 1600, 0, False, False), (1600, 1400, 0, False, False),
    (1401, 1401, 0, False, True), (1600, 1600, 1, False, False),
    (1600, 1600, 0, True, False),
])
def test_original_longlong_reset_selector_preserves_its_analog_and_safety_gates(
    originals, throttle, brake, speed, locked, selected,
):
    assert BleConstraints(originals.app).reserved_reset_selection(
        throttle, brake, speed=speed, locked=locked) is selected
    # Der eigentliche Reset ist abgefangen und weder getestet noch verändert.


@pytest.mark.parametrize('brake', [0, 1, 32, 100])
def test_original_mcu_brake_function_uses_the_forwarded_value_without_ssm(originals, brake):
    machine = McuConstraints(originals.mcu)
    machine.seed(0x20000234, bytes((brake,)))
    row = machine.brake_control_step()
    assert row['brake_scaled'] == (brake << 15) // 100
    assert row['brake_active_262'] == row['brake_active_263'] == int(brake > 0)
    assert not row['physical_braking_proven']


@pytest.mark.parametrize('mode', range(16))
def test_complete_original_control_function_keeps_clamp_and_has_no_fourth_mode(originals, mode):
    machine = McuConstraints(originals.mcu)
    machine.select_limits(b'60556')
    machine.seed(0x20000229, bytes((mode,)))
    expected = {11: 125, 2: 313, 3: 417}.get(mode, 208)
    first = machine.control_step()
    second = machine.control_step()
    assert first['selected_limit_raw'] == first['controller_setpoint_raw'] == expected
    assert first['original_clamp_executed'] and second['original_clamp_executed']
    assert second['setpoint_read_by_control']
    assert first['minimum_sp'] == second['minimum_sp'] == 0x20001b74
    assert not first['motor_effect_proven']


def test_original_regulator_phase_and_output_do_not_form_a_limit_ack(originals):
    machine = McuConstraints(originals.mcu)
    machine.select_limits(b'60556')
    machine.seed(0x20000229, b'\x03')
    machine.seed(0x20000224, struct.pack('<I', 5000))
    machine.seed(0x20001760, struct.pack('<I', 5000))
    first, second = machine.control_step(), machine.control_step()
    assert not first['setpoint_read_by_control'] and second['setpoint_read_by_control']
    assert second['control_output_raw'] == second['control_output_mirror_raw'] == 5000
    assert second['reported_speed_raw'] == 0  # Ausgang und Geschwindigkeit sind verschiedene Grössen.
    assert machine.read(0x20000224, 4) == struct.pack('<I', 5000)  # Kein erfundener PID->FOC-Draht.
    assert second['selected_limit_raw'] == 417


def test_original_brake_flag_takes_priority_over_the_speed_pi_branch(originals):
    machine = McuConstraints(originals.mcu)
    machine.select_limits(b'60556')
    machine.seed(0x20000229, b'\x03')
    machine.seed(0x20000224, struct.pack('<I', 5000))
    machine.seed(0x20001760, struct.pack('<I', 5000))
    machine.seed(0x20000234, b'\x20')
    machine.brake_control_step()
    first, second = machine.control_step(), machine.control_step()
    assert not second['setpoint_read_by_control']
    assert first['selected_limit_raw'] == second['selected_limit_raw'] == 417
    assert second['control_output_raw'] == 0
    assert machine.read(0x20000263, 1) == b'\x01'


def test_mode_unchanged_can_leave_old_setpoint_under_original_ramp_gate(originals):
    machine = McuConstraints(originals.mcu)
    machine.select_limits(b'60556')
    machine.seed(0x20000229, b'\x03')
    machine.seed(0x20000320, b'\x03')
    machine.seed(0x20000333, b'\x01')
    machine.seed(0x200003f2, struct.pack('<H', 200))
    results = [machine.control_step() for _ in range(7)]
    assert all(r['selected_limit_raw'] == 417 for r in results)
    assert [r['controller_setpoint_raw'] for r in results] == [200] * 6 + [201]
    assert all(r['original_clamp_executed'] for r in results)
    # Ein zusätzlicher Unterzustand bei unverändertem Sport bräuchte diese Zustandslogik.


def test_same_status_can_hide_different_setpoints_with_the_same_selected_limit(originals):
    report = constraints_report(originals.ble, originals.mcu)
    old, new = report['same_mode_different_setpoint']
    assert old['selected_limit_raw'] == new['selected_limit_raw'] == 417
    assert old['controller_setpoint_raw'] == 200 and new['controller_setpoint_raw'] == 417
    assert len(set(report['status_for_different_setpoints'])) == 1
    assert report['status_has_applied_limit_ack'] is False
    assert not report['new_speed_state_implemented'] and not report['ssm_hooks_injected']


def test_task_request_is_evidence_of_requested_stack_not_available_reserve(originals):
    row = BleConstraints(originals.app).task_creation()
    assert row['address'] == 0x269d0 and row['r0'] == 0x2081a4
    assert row['r1'] == APP_BASE + 0x25ec and row['r2'] == APP_BASE + 0x2447
    assert row['r3'] == 0 and row['stack_arguments'] == [8192, 1]
    assert row['kind'] == 'task_create_not_executed'


def test_callback_reference_scan_is_explicitly_incomplete(originals):
    result = reference_candidates(originals.app, {0x9e18, 0x82d4, 0x60f4, 0xc6b2})
    assert not result['complete_control_flow_proven']
    assert {'source_app_offset': 0xc384, 'target_app_offset': 0x9e18,
            'kind': 'aligned_thumb_pointer_candidate'} in result['candidates']
    assert {'source_app_offset': 0x9e2a, 'target_app_offset': 0x82d4,
            'kind': 'direct_branch_candidate'} in result['candidates']


@pytest.mark.parametrize('entry,pc,address', [(0x1b67c, 0x1c7e2, 0x40012c54),
                                            (0x1a938, 0x1be20, 0x40012c54)])
def test_unknown_motor_periphery_stops_analysis_instead_of_fabricating_feedback(
    originals, entry, pc, address,
):
    machine = McuConstraints(originals.mcu)
    machine.select_limits(b'60556')
    machine.seed(0x20000229, b'\x03')
    machine.control_step()
    machine.control_step()
    result = machine.peripheral_boundary(entry)
    assert result['blocked'] and not result['peripheral_model_supplied']
    assert result['unmapped']['pc_file_offset'] == pc
    assert result['unmapped']['address'] == address


def test_returning_inactive_motor_path_does_not_prove_complete_execution(originals):
    result = McuConstraints(originals.mcu).peripheral_boundary(0x1b67c)
    assert not result['blocked'] and not result['whole_function_coverage_proven']
