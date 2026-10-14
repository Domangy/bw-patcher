#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Neue Container- und Originalcodeprüfungen; keine Scooter-Hardwaretests."""

import hashlib
import lzma
import os
from pathlib import Path
import struct

import pytest

from bwpatcher.mi5pro_research import (
    APP_BASE, APP_SHA256, AnalysisError, BLOCK_LAST, BLOCK_MORE,
    checked_slice, control_header, decode_compressed_app, hook_candidates,
    inspect_ble, normal_image_digest, thumb_evidence,
)


def normal_image(image_id=0x2793, body=b"synthetische Daten" * 100):
    image = bytearray(0x400) + body
    struct.pack_into("<BBHHHI", image, 0, 5, 0, 0x101, image_id, 0, len(body))
    image[12:28] = bytes(range(16))
    struct.pack_into("<I", image, 0x28, APP_BASE)
    image[0x174:0x194] = bytes.fromhex(normal_image_digest(image)["computed"])
    return bytes(image)


def compact(payload):
    header = bytearray(96)
    struct.pack_into("<BBHHHI", header, 0, 5, 0, 0x2181, 0x2793, 0, len(payload))
    header[12:28] = bytes(range(16))
    struct.pack_into("<I", header, 32, 1)
    header[36:68] = hashlib.sha256(payload).digest()
    return header + payload


def compress_image(image, chunk_size=0x4000):
    chunks = [image[o:o + chunk_size] for o in range(0, len(image), chunk_size)]
    payload = bytearray()
    for i, chunk in enumerate(chunks):
        packed = lzma.compress(chunk, format=lzma.FORMAT_ALONE, filters=[
            {"id": lzma.FILTER_LZMA1, "dict_size": 4096},
        ])
        payload += struct.pack("<IHH", BLOCK_LAST if i == len(chunks) - 1 else BLOCK_MORE,
                               len(chunk), len(packed))
        payload += packed
    payload += b"\xff" * (-len(payload) % 4)
    return compact(payload)


def test_synthetic_container_roundtrip_preserves_input():
    app = normal_image()
    compressed = compress_image(app, 512)
    patch = normal_image(0x2792)
    package = patch + b"\xff" * (-len(patch) % 16) + compressed
    before = bytes(package)
    decoded = inspect_ble(package)
    assert decoded.app == app
    assert decoded.report["patch_digest"]["valid"]
    assert decoded.report["decoded_image_digest"]["valid"]
    assert len(decoded.report["blocks"]) > 1
    assert not decoded.report["ssm_patch_available"]
    assert bytes(package) == before


@pytest.mark.parametrize("cut", [0, 11, 95, 96, 110, -1])
def test_truncation_is_rejected(cut):
    data = compress_image(normal_image())
    with pytest.raises(AnalysisError):
        decode_compressed_app(data[:cut], 0)


def test_compressed_digest_is_checked_before_decoder():
    data = compress_image(normal_image())
    data[-1] ^= 1
    with pytest.raises(AnalysisError, match="SHA-256 des komprimierten"):
        decode_compressed_app(data, 0)


@pytest.mark.parametrize("mutation,match", [
    (lambda p: struct.pack_into("<I", p, 0, 0x12345678), "Blockmarkierung"),
    (lambda p: struct.pack_into("<H", p, 4, 0), "Blocklänge"),
    (lambda p: struct.pack_into("<H", p, 4, 0xffff), "Blocklänge"),
    (lambda p: struct.pack_into("<H", p, 6, 12), "Blocklänge"),
    (lambda p: struct.pack_into("<H", p, 6, 0xffff), "ausserhalb"),
    (lambda p: p.__setitem__(8, 0xff), "LZMA-Block"),
    (lambda p: struct.pack_into("<I", p, 9, 0x40000000), "LZMA-Block"),
])
def test_hash_correct_but_invalid_stream_is_rejected(mutation, match):
    payload = bytearray(compress_image(normal_image())[96:])
    mutation(payload)
    with pytest.raises(AnalysisError, match=match):
        decode_compressed_app(compact(payload), 0)


def test_wrong_declared_output_length_is_rejected():
    data = compress_image(normal_image())
    payload = bytearray(data[96:])
    count = struct.unpack_from("<H", payload, 4)[0]
    struct.pack_into("<H", payload, 4, count - 1)
    with pytest.raises(AnalysisError, match="Streamende"):
        decode_compressed_app(compact(payload), 0)


def test_valid_compression_does_not_hide_invalid_inner_digest():
    data = bytearray(normal_image())
    data[-1] ^= 1
    with pytest.raises(AnalysisError, match="entpackten APP"):
        decode_compressed_app(compress_image(data), 0)


def test_unexpected_trailing_payload_is_rejected():
    data = compress_image(normal_image())
    payload = data[96:] + b"\xff" * 4
    with pytest.raises(AnalysisError, match="Padding"):
        decode_compressed_app(compact(payload), 0)


@pytest.mark.parametrize("position,value", [(0, 4), (3, 1), (4, 0), (32, 2)])
def test_unsupported_header_fields_are_rejected(position, value):
    data = compress_image(normal_image())
    data[position] = value
    with pytest.raises(AnalysisError):
        decode_compressed_app(data, 0)


def test_uuid_mismatch_is_rejected_even_with_valid_digests():
    patch = bytearray(normal_image(0x2792))
    patch[12] ^= 1
    patch[0x174:0x194] = bytes.fromhex(normal_image_digest(patch)["computed"])
    with pytest.raises(AnalysisError, match="UUID"):
        inspect_ble(patch + b"\xff" * (-len(patch) % 16) + compress_image(normal_image()))


def test_code_sites_are_never_applied_to_synthetic_image():
    with pytest.raises(AnalysisError, match="exakt untersuchte APP"):
        thumb_evidence(normal_image(), 0x400, 4)


@pytest.fixture(scope="module")
def originals():
    directory = os.environ.get("MI5PRO_FIRMWARE_DIR")
    if not directory:
        pytest.skip("Lokale Originaldateien erforderlich; keine Binärdateien im Repository.")
    base = Path(directory)
    ble = (base / "ble_2.7.0_0015.bin").read_bytes()
    mcu = (base / "mcu_0007.bin").read_bytes()
    from bwpatcher.ssm_firmware import ORIGINALS
    assert hashlib.sha256(ble).hexdigest() == ORIGINALS["ble"]["sha256"]
    assert hashlib.sha256(mcu).hexdigest() == ORIGINALS["mcu"]["sha256"]
    return inspect_ble(ble), mcu


@pytest.fixture
def emu(originals):
    pytest.importorskip("unicorn")
    from bwpatcher.mi5pro_emulator import OriginalAppEmulator
    return OriginalAppEmulator(originals[0].app)


def test_exact_original_decompression_and_three_digests(originals):
    decoded, _ = originals
    report = decoded.report
    assert len(decoded.app) == 181612
    assert hashlib.sha256(decoded.app).hexdigest() == APP_SHA256
    assert len(report["blocks"]) == 12
    assert [b["unpacked_size"] for b in report["blocks"]] == [16384] * 11 + [1388]
    assert report["compressed_offset"] == 0xa000
    assert report["patch_digest"]["computed"] == (
        "e46b3499cd6e90eb3c8513b8658634e2b6b12342a913b4fed962cc14b9176f3d"
    )
    assert report["decoded_image_digest"]["computed"] == (
        "cd7638f9e2bc797a57e20325f5a42606583111e0fe6d2120999333a022740cfe"
    )
    assert report["decoded_image_base"] == APP_BASE


def test_hook_candidates_have_instruction_boundaries_but_no_injection_approval(originals):
    decoded, _ = originals
    sites = hook_candidates(decoded.app, decoded.report["blocks"])
    assert [s["app_offset"] for s in sites] == [0x8264, 0x82fc, 0x8550, 0x611c, 0xc76c]
    assert sites[0]["branch_target"] == APP_BASE + 0x81ce
    assert sites[1]["branch_target"] == APP_BASE + 0x8260
    assert sites[2]["branch_target"] == APP_BASE + 0x80aa
    assert all(s["continuation_address"] == s["address"] + 4 for s in sites)
    assert all(not s["approved_for_injection"] for s in sites)
    assert all(not s["direct_ota_byte_offset_exists"] for s in sites)


def test_timer_and_io_callbacks_resolve_to_the_key_handler(originals):
    app = originals[0].app
    timer = thumb_evidence(app, 0x19712, 0x12)
    registered = thumb_evidence(app, 0xc05c, 0x8)
    handler = thumb_evidence(app, 0x9e18, 0x1c)
    assert any(row.get("reference_address") == APP_BASE + 0x9e35 for row in timer)
    assert any(row.get("reference_address") == APP_BASE + 0x9e19 for row in registered)
    assert any(row.get("branch_target") == APP_BASE + 0x82d4 for row in handler)


@pytest.mark.parametrize("count,events", [(1, [(59, 1)]), (2, [(25, 2)]),
    (5, [(25, 2), (57, 2), (73, 5), (123, 1)])])
def test_original_button_classifier_really_emits_double_before_fifth(emu, count, events):
    trace = emu.click_trace(count)
    assert [(e["tick"], e["event"]) for e in trace] == events


def test_original_long_hold_and_release_events(emu):
    events = []
    for tick in range(800):
        event = emu.button_tick(tick < 750)
        if event:
            events.append((tick + 1, event))
    assert events[:2] == [(252, 3), (702, 6)]
    assert any(e == 7 for _, e in events)


def display_registers(trace):
    address = None
    registers = {}
    for kind, value in trace:
        if kind == "display_command" and 0xc0 <= value <= 0xcc:
            address = value
        elif kind == "display_data":
            registers[address] = value
    return registers


@pytest.mark.parametrize("mask", [1, 2, 4, 7])
def test_original_renderer_serializes_three_independent_mode_bits(emu, mask):
    values = [0] * 21
    values[12] = mask
    result = display_registers(emu.display_trace(values))
    assert result == {0xc0: 0, 0xc2: 0, 0xc4: 0, 0xc6: 0, 0xc8: mask, 0xca: 0, 0xcc: 0}


def test_mode_overlay_preserves_other_display_outputs_and_motor_state(emu):
    values = [0x10] * 21
    values[1], values[6], values[7], values[8] = 0x10, 0x20, 0x80, 0x08
    emu.uc.mem_write(emu.INFO, b"\xa5" * 0x80)
    values[12] = 1
    before = display_registers(emu.display_trace(values))
    values[12] = 7
    after = display_registers(emu.display_trace(values))
    assert after[0xc8] == before[0xc8] | 7
    assert {k: v for k, v in before.items() if k != 0xc8} == {k: v for k, v in after.items() if k != 0xc8}
    assert bytes(emu.uc.mem_read(emu.INFO, 0x80)) == b"\xa5" * 0x80
    for _ in range(10):
        emu.call(0xc6b2, stubs={APP_BASE + 0xc4a6: "display_command",
            APP_BASE + 0xc44a: "display_data", 0x113dc: "pin_configuration"})
        assert display_registers(emu.calls) == after


@pytest.mark.parametrize("mask", [1, 2, 4, 7])
def test_original_copy_path_preserves_bitmap_and_does_not_change_drive_mode(emu, mask):
    emu.uc.mem_write(emu.INFO + 1, b"\x03")
    emu.uc.mem_write(0x208660, bytes((mask,)))
    emu.call(0x60f4)
    assert bytes(emu.uc.mem_read(emu.DISPLAY + 0x60, 1)) == bytes((mask,))
    assert bytes(emu.uc.mem_read(emu.INFO + 1, 1)) == b"\x03"
    assert all(emu.last_abi.values())


@pytest.mark.parametrize("mode", [11, 2, 3])
@pytest.mark.parametrize("upper", [1, 2, 3])
def test_original_ble_builder_to_original_mcu_field_consumer(emu, originals, mode, upper):
    from bwpatcher.mi5pro_emulator import consume_mode_fragment
    frame = emu.controller_frame(mode, upper)
    assert frame[:3] == b"\x51\x10\x07"
    assert frame[3] == upper << 4 | mode
    assert frame[-2] == sum(frame[:-2]) & 255
    assert consume_mode_fragment(originals[1], frame) == {"mode": mode, "upper_nibble": upper}


def test_corrupted_uart_frame_is_rejected(originals):
    pytest.importorskip("unicorn")
    from bwpatcher.mi5pro_emulator import consume_mode_fragment
    with pytest.raises(AnalysisError, match="Prüfsumme"):
        consume_mode_fragment(originals[1], bytes.fromhex("511007230000000000008aae"))


def test_unknown_external_calls_and_short_budget_fail_explicitly(emu):
    with pytest.raises(AnalysisError, match="externer Aufruf"):
        emu.call(0xc4a6)  # Pin-Konfiguration im ROM wurde hier nicht freigegeben.
    with pytest.raises(AnalysisError, match="Budgets"):
        emu.call(0x8260, budget=1)
    with pytest.raises(AnalysisError, match="budget"):
        emu.call(0x8260, budget=0)


def test_six_dense_presses_include_reserved_five_event(emu):
    assert [(row['tick'], row['event']) for row in emu.click_trace(6)] == [
        (25, 2), (57, 2), (73, 5), (89, 2),
    ]


@pytest.mark.parametrize('pause', [40, 50, 60, 80, 120])
def test_three_separate_pairs_produce_only_three_original_doubles(emu, pause):
    trace = emu.click_trace(6, pair_pause_ticks=pause)
    assert [row['event'] for row in trace] == [2, 2, 2]
    assert [row['tick'] for row in trace] == [25, 57 + pause, 89 + 2 * pause]


@pytest.mark.parametrize('start,expected', [
    (3, [11, 2, 3]), (11, [2, 3, 11]), (2, [3, 11, 2]),
])
def test_original_dispatcher_executes_all_three_normal_mode_changes(emu, start, expected):
    emu.uc.mem_write(emu.INFO + 1, bytes((start,)))
    emu.uc.mem_write(emu.INFO + 0xe, b'\x01')
    trace = emu.click_trace(6, pair_pause_ticks=60, dispatch=True)
    assert [row['event'] for row in trace] == [2, 2, 2]
    assert [row['mode_after'] for row in trace] == expected
    assert all(row['mode_cycle_called'] for row in trace)
    assert all(emu.last_abi.values())


def test_original_dispatcher_retains_its_mode_gate(emu):
    emu.uc.mem_write(emu.INFO + 1, b'\x03')
    emu.uc.mem_write(emu.INFO + 0xe, b'\x01')
    emu.uc.mem_write(emu.INFO + 0x10, b'\x01')
    trace = emu.click_trace(6, pair_pause_ticks=60, dispatch=True)
    assert [row['event'] for row in trace] == [2, 2, 2]
    assert [row['mode_after'] for row in trace] == [3, 3, 3]
    assert not any(row['mode_cycle_called'] for row in trace)


def test_original_single_click_toggles_emulated_light_output_without_mode_change(emu):
    emu.uc.mem_write(emu.INFO + 1, b'\x03')
    emu.uc.mem_write(emu.INFO + 0xe, b'\x01')
    emu.uc.mem_write(0x208660, b'\x04')
    emu.uc.mem_write(0x40001000, struct.pack('<I', 0xa5a50000))
    for output in (0xa5a50040, 0xa5a50000):
        trace = emu.click_trace(1, dispatch=True)
        assert [row['event'] for row in trace] == [1]
        assert trace[0]['mode_after'] == 3 and not trace[0]['mode_cycle_called']
        assert struct.unpack('<I', bytes(emu.uc.mem_read(0x40001000, 4)))[0] == output
        assert bytes(emu.uc.mem_read(0x208660, 1)) == b'\x04'


@pytest.mark.parametrize('pause,activate', [(0, False), (20, False), (60, True)])
def test_original_dispatcher_events_and_actual_modes_drive_event_simulation(
    emu, originals, pause, activate,
):
    from bwpatcher.ssm import Action, Inputs, Mode, State, SuperSportSimulation
    from bwpatcher.mi5pro_emulator import OriginalAppEmulator, consume_mode_fragment
    from dataclasses import replace
    mapping = {11: Mode.WALK, 2: Mode.DRIVE, 3: Mode.SPORT}
    emu.uc.mem_write(emu.INFO + 1, b'\x03')
    emu.uc.mem_write(emu.INFO + 0xe, b'\x01')
    trace = emu.click_trace(6, pair_pause_ticks=pause, dispatch=True)
    inputs = Inputs(powered=True, mode=Mode.SPORT, speed_mm_s=0, fault=False,
                    throttle_released=True, locked=False, telemetry_valid=True,
                    oem_reserved=False)
    model = SuperSportSimulation(enabled=True)
    builder = OriginalAppEmulator(originals[0].app)
    model.sample(0, None, inputs)
    model.sample(600, None, inputs)
    actions = []
    for row in trace:
        now = 600 + row['nominal_ms']
        actions.extend(model.sample(now, row['event'], inputs))
        if row['mode_cycle_called']:
            ticket = model.pending_mode_request.ticket
            frame = builder.controller_frame(row['mode_after'], 2)
            consumed = consume_mode_fragment(originals[1], frame)
            assert consumed['mode'] == row['mode_after']
            inputs = replace(inputs, mode=mapping[consumed['mode']])
            actions.extend(model.sample(now + 1, None, inputs, mode_ack=ticket))
    assert actions.count(Action.NEXT_MODE) == 3
    assert (Action.ACTIVATE in actions) is activate
    assert (model.state is State.ACTIVE) is activate
    if activate:
        assert model.display({})['mode_icons'] == frozenset(Mode)
        assert model.sample(now + 920, 2, inputs) == [Action.DEACTIVATE]
        assert model.inputs.mode is Mode.SPORT
    else:
        assert Action.OEM_EVENT in actions
