#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Neue Originalnachweise; keine injizierten Hooks und keine Hardwaretests."""

import os
from pathlib import Path
import struct
from dataclasses import dataclass

import pytest

from bwpatcher.mi5pro_integration import (
    BleIntegration, McuOriginal, MCU_RAM, MCU_STACK,
    ble_memory_layout, decode_status, integration_report,
)
from bwpatcher.mi5pro_emulator import OriginalAppEmulator
from bwpatcher.mi5pro_research import AnalysisError, inspect_ble


def status(mode=3, upper=2, speed=0):
    frame = bytearray.fromhex('61300a23000000000000000000009e')
    frame[3] = upper << 4 | mode
    frame[9:11] = speed.to_bytes(2, 'big')
    frame[-2] = sum(frame[:-2]) & 255
    return bytes(frame)


@pytest.mark.parametrize('mode', [11, 2, 3])
@pytest.mark.parametrize('speed', [0, 49, 50, 1000])
def test_strict_status_observer_preserves_raw_fields_without_claiming_limit_ack(mode, speed):
    decoded = decode_status(status(mode, speed=speed))
    assert decoded['echoed_mode'] == mode and decoded['speed_raw'] == speed
    assert not decoded['confirms_applied_speed_limit']
    assert not decoded['wire_sequence_number_present']


@pytest.mark.parametrize('mutation', [
    lambda f: f[:4], lambda f: f[:-1], lambda f: f + b'\0',
    lambda f: bytes((0x62,)) + f[1:],
    lambda f: f[:1] + b'\x31' + f[2:],
    lambda f: f[:2] + b'\x09' + f[3:],
    lambda f: f[:-2] + bytes((f[-2] ^ 1,)) + f[-1:],
    lambda f: f[:-1] + b'\x00',
])
def test_strict_status_rejects_incomplete_or_inconsistent_frames(mutation):
    with pytest.raises(AnalysisError):
        decode_status(mutation(status()))


@pytest.mark.parametrize('mode,upper', [(0, 2), (7, 2), (3, 0), (3, 4)])
def test_unknown_mode_states_are_not_trusted_even_with_valid_checksum(mode, upper):
    with pytest.raises(AnalysisError, match='Moduszustand'):
        decode_status(status(mode, upper))


def test_short_but_checksum_consistent_frame_cannot_be_used_as_telemetry():
    with pytest.raises(AnalysisError):
        decode_status(bytes.fromhex('613000919e'))


def test_unknown_images_do_not_reach_emulation_or_address_analysis():
    with pytest.raises(AnalysisError):
        McuOriginal(b'not firmware')
    with pytest.raises(AnalysisError):
        ble_memory_layout(b'not firmware')


@pytest.fixture(scope='module')
def originals():
    directory = os.environ.get('MI5PRO_FIRMWARE_DIR')
    if not directory:
        pytest.skip('Lokale Originale erforderlich; keine Firmware im Repository.')
    pytest.importorskip('unicorn')
    base = Path(directory)
    ble = (base / 'ble_2.7.0_0015.bin').read_bytes()
    mcu = (base / 'mcu_0007.bin').read_bytes()
    return OriginalFiles((ble, mcu, inspect_ble(ble).app))


@dataclass(repr=False)
class OriginalFiles:
    data: tuple

    def __getitem__(self, index):
        return self.data[index]


@pytest.fixture
def mcu(originals):
    return McuOriginal(originals[1])


def test_ble_initialization_marks_used_memory_without_reserving_private_ssm_ram(originals):
    app = originals[2]
    layout = ble_memory_layout(app)
    assert [(r['source_app_offset'], r['destination'], r['size']) for r in layout['copies']] == [
        (0x2bff4, 0x207c00, 0x124), (0x2c118, 0x207d24, 0x454),
    ]
    assert layout['zero'] == {'destination': 0x208178, 'size': 0x3c08, 'end': 0x20bd80}
    assert not layout['private_ram_reserved'] and not layout['executable_extension_reserved']
    machine = BleIntegration(app)
    for r in layout['copies']:
        assert bytes(machine.uc.mem_read(r['destination'], r['size'])) == app[
            r['source_app_offset']:r['source_app_offset'] + r['size']
        ]
    assert bytes(machine.uc.mem_read(0x208178, 0x3c08)) == b'\0' * 0x3c08
    assert layout['synthetic_emulator_stack'] > layout['zero']['end']


def test_mcu_scatter_decompression_and_original_stack_boundaries(mcu):
    assert mcu.scatter == [(0xab34, MCU_RAM, 0x838, 0x9cc),
                           (0xae90, MCU_RAM + 0x838, 0x1370, 0x83d4)]
    assert MCU_RAM + 0x838 + 0x1370 == MCU_STACK
    assert mcu.initial_limits == [417, 417, 313, 417, 313, 417, 313,
                                  522, 522, 417, 522, 417, 668, 417]
    assert mcu.read(MCU_RAM + 0x838, 0x1370) == b'\0' * 0x1370
    with pytest.raises(AnalysisError):
        mcu.seed(MCU_STACK, b'\0')


REGIONS = [
    (b'60550', 417, 522), (b'60555', 417, 522), (b'60556', 313, 417),
    (b'60557', 417, 522), (b'60561', 313, 417), (b'60564', 417, 668),
    (b'61143', 313, 417),
]


@pytest.mark.parametrize('prefix,drive,sport', REGIONS)
@pytest.mark.parametrize('mode', [11, 2, 3])
def test_original_prefix_selection_and_unmodified_speed_selection(mcu, prefix, drive, sport, mode):
    result = mcu.select_limits(prefix)
    assert (result['drive_raw'], result['sport_raw']) == (drive, sport)
    assert result['index'] == [p for p, _, _ in REGIONS].index(prefix)
    assert mcu.speed_selection(mode) == {11: 125, 2: drive, 3: sport}[mode]


@pytest.mark.parametrize('prefix,drive,sport', REGIONS)
def test_original_additional_clamp_remains_effective_with_override_flag(mcu, prefix, drive, sport):
    mcu.select_limits(prefix)
    assert mcu.speed_selection(3, override_flag=1) == min(522, sport)


def test_original_clamp_catches_synthetic_drive_above_sport_cap(mcu):
    mcu.select_limits(b'60556')
    mcu.seed(0x20000324, struct.pack('<H', 1000))  # Nur emulierter RAM, keine Firmwareänderung.
    assert mcu.speed_selection(2) == 417
    assert mcu.speed_selection(7) == 208  # Kein vierter SSM-Modus im Original.


@pytest.mark.parametrize('mode', [11, 2, 3])
@pytest.mark.parametrize('upper', [1, 2, 3])
def test_original_tx_to_mcu_echo_and_ble_receiver_roundtrip(originals, mcu, mode, upper):
    sender = OriginalAppEmulator(originals[2])
    mcu.consume_mode(sender.controller_frame(mode, upper))
    frame = mcu.status_frame()
    result = decode_status(frame)
    assert result['echoed_mode'] == mode and result['upper_nibble'] == upper
    receiver = BleIntegration(originals[2])
    requested = 2 if mode != 2 else 3
    receiver.uc.mem_write(receiver.INFO + 1, bytes((requested,)))
    feedback = receiver.receive_raw(frame)
    assert feedback['status_30_dispatched']
    assert feedback['feedback_mode'] == mode
    assert feedback['feedback_upper'] == upper
    assert feedback['requested_mode'] == requested  # Echo ist ein getrenntes RAM-Feld.
    assert feedback['feedback_speed_raw_or_adjusted'] == 0


@pytest.mark.parametrize('bad', ['checksum', 'trailer', 'length'])
def test_original_receiver_rejects_corrupted_status_without_replacing_mode(originals, bad):
    receiver = BleIntegration(originals[2])
    receiver.uc.mem_write(0x2082d1, b'\x0b')
    frame = bytearray(status())
    if bad == 'checksum':
        frame[-2] ^= 1
    elif bad == 'trailer':
        frame[-1] ^= 1
    else:
        frame = frame[:-1]
    assert not receiver.receive_raw(frame)['status_30_dispatched']
    assert bytes(receiver.uc.mem_read(0x2082d1, 1)) == b'\x0b'


def test_original_receiver_length_check_is_insufficient_for_fixed_status_shape(originals):
    short = bytes.fromhex('613000919e')
    original_result = BleIntegration(originals[2]).receive_raw(short)
    assert original_result['status_30_dispatched']  # Tatsächlicher Originalpfad, kein Mock.
    assert original_result['feedback_mode'] == 1
    with pytest.raises(AnalysisError):
        decode_status(short)  # Der neue Beobachter gibt daraus keine Freigabe.


def test_identical_status_can_mean_two_different_original_speed_limits(originals):
    observed = []
    for prefix in (b'60556', b'60564'):
        mcu = McuOriginal(originals[1])
        mcu.select_limits(prefix)
        mcu.seed(0x20000228, b'\x02\x03')
        frame = mcu.status_frame()
        observed.append((frame, mcu.speed_selection(3)))
    assert observed[0][0] == observed[1][0]
    assert [r[1] for r in observed] == [417, 668]
    assert not decode_status(observed[0][0])['confirms_applied_speed_limit']


def test_sport_echo_can_precede_new_limit_calculation(originals, mcu):
    mcu.select_limits(b'60556')
    assert mcu.speed_selection(2) == 313
    sender = OriginalAppEmulator(originals[2])
    mcu.consume_mode(sender.controller_frame(3, 2))
    assert decode_status(mcu.status_frame())['echoed_mode'] == 3
    assert struct.unpack('<H', mcu.read(0x2000177c, 2))[0] == 313
    assert mcu.speed_selection(3) == 417


@pytest.mark.parametrize('gate', [0x20000339, 0x20000358])
def test_original_sender_session_gates_suppress_feedback(mcu, gate):
    mcu.seed(0x20000228, b'\x02\x03')
    mcu.seed(gate, b'\x01')
    assert mcu.status_frame() is None


def test_original_status_scheduler_has_no_immediate_per_request_ack(mcu):
    mcu.seed(0x20000228, b'\x02\x03')
    frames = []
    for tick in (0, 0, 1600, 1601, 1601, 3201):
        mcu.seed(0x200001e0, struct.pack('<Q', tick))
        frames.append(mcu.status_frame())
    assert frames[0] == frames[4]
    assert frames[1:4] == [None] * 3
    assert frames[5][:3] == b'\x61\x31\x09'  # Andere Nachricht, keine Modusquittung.
    with pytest.raises(AnalysisError):
        decode_status(frames[5])


def test_actual_hook_contexts_survive_volatile_abi_clobbering(originals):
    report = integration_report(originals[0], originals[1])
    contexts = {s['app_offset']: s for s in report['hook_contexts']}
    for before, after in [(0x8264, 0x8268), (0x82fc, 0x8300), (0x8550, 0x8554),
                          (0x611c, 0x6120), (0xc76c, 0xc770)]:
        assert contexts[before]['sp'] == contexts[after]['sp']
        assert contexts[before]['itstate'] == contexts[after]['itstate'] == 0
        if before in (0x8264, 0x82fc, 0x8550):
            for reg in (f'r{i}' for i in range(4, 12)):
                assert contexts[before][reg] == contexts[after][reg]
    assert contexts[0x82fc]['sp'] == contexts[0x8550]['sp'] == 0x20ffc8
    assert contexts[0x8264]['sp'] == contexts[0xc76c]['sp'] == 0x20ffc0
    assert contexts[0x611c]['sp'] == 0x20ffe0
    for reg in (f'r{i}' for i in range(4, 12)):
        assert contexts[0x8550][reg] == contexts[0x8554][reg]
    assert contexts[0x8554]['r1'] == 0xccdd0000
    assert contexts[0x8554]['apsr'] != contexts[0x8550]['apsr']
    assert contexts[0x611c] | {'app_offset': 0x6120} == contexts[0x6120]
    assert contexts[0xc770]['r0'] == 4  # Original-LDRB; keine Overlay-Injektion.
    assert contexts[0xc76c] | {'app_offset': 0xc770, 'r0': 4} == contexts[0xc770]
    assert report['synthetic_stack_minimum_in_selected_calls'] == 0x20ffb0
    assert not report['ssm_patch_available'] and not report['hardware_validated']
