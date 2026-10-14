#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""OEM-Ereignisse und bestätigte Modusaktionen; keine Hardwaretests."""

from dataclasses import replace
import random

import pytest

from bwpatcher.ssm import (
    Action, Inputs, Mode, State, SuperSportSimulation, Timing, next_stock_mode,
)


READY = Inputs(
    powered=True, mode=Mode.SPORT, speed_mm_s=0, fault=False,
    throttle_released=True, locked=False, telemetry_valid=True, oem_reserved=False,
)


class Rig:
    def __init__(self, *, enabled=True, inputs=READY, timing=Timing()):
        self.model = SuperSportSimulation(enabled=enabled, timing=timing)
        self.inputs = inputs
        self.now = 0
        self.actions = self.model.sample(0, None, inputs)
        self.wait(600)

    def send(self, event=None, *, delay=10, ack=None, dashboard=False, **changes):
        self.now += delay
        self.inputs = replace(self.inputs, **changes)
        actions = self.model.sample(
            self.now, event, self.inputs, mode_ack=ack, dashboard_event=dashboard,
        )
        self.actions.extend(actions)
        return actions

    def wait(self, duration, **changes):
        self.inputs = replace(self.inputs, **changes)
        for _ in range(duration // 10):
            self.send(delay=10)

    def confirm(self, **changes):
        request = self.model.pending_mode_request
        assert request is not None
        changes.setdefault('mode', request.target)
        return self.send(ack=request.ticket, **changes)

    def double(self, *, delay=920, ack=True):
        self.wait(delay)
        result = self.send(2)
        if ack and Action.NEXT_MODE in result:
            self.confirm()
        return result

    def activate(self):
        for _ in range(3):
            self.double()
        assert self.model.state is State.ACTIVE
        self.actions.clear()


def test_three_oem_doubles_cycle_all_stock_modes_before_activation():
    rig = Rig()
    observed = []
    for expected in (Mode.WALK, Mode.DRIVE, Mode.SPORT):
        rig.double(ack=False)
        assert rig.model.state is State.NORMAL
        assert rig.actions.count(Action.NEXT_MODE) == len(observed) + 1
        rig.confirm()
        observed.append(rig.inputs.mode)
        assert observed[-1] is expected
    assert rig.actions == [Action.NEXT_MODE] * 3 + [Action.ACTIVATE]
    assert rig.model.speed_override_kmh == 30


@pytest.mark.parametrize('start', [Mode.WALK, Mode.DRIVE])
def test_third_stock_cycle_must_actually_finish_in_sport(start):
    rig = Rig(inputs=replace(READY, mode=start))
    for _ in range(3):
        rig.double()
    assert rig.inputs.mode is start
    assert rig.model.state is State.NORMAL
    assert rig.actions == [Action.NEXT_MODE] * 3
    assert rig.model.double_count == 0


def test_preexisting_sport_or_unacknowledged_mode_update_cannot_activate():
    rig = Rig(inputs=replace(READY, mode=Mode.WALK))
    rig.double()
    rig.double()
    assert rig.inputs.mode is Mode.SPORT  # Vor dem dritten Wechsel, nicht danach.
    rig.double(ack=False)
    rig.wait(100)
    assert rig.model.state is State.NORMAL
    rig.confirm()  # Dritter OEM-Wechsel führt tatsächlich zu Walk.
    assert Action.ACTIVATE not in rig.actions
    rig = Rig()
    rig.double()
    rig.double()
    rig.double(ack=False)
    rig.send(mode=Mode.SPORT)  # Snapshot allein ist keine Abschlussquittung.
    assert rig.model.state is State.NORMAL
    rig.confirm()
    assert rig.model.state is State.ACTIVE


@pytest.mark.parametrize('ack_kind', ['wrong_ticket', 'wrong_mode', 'timeout', 'no_ack'])
def test_missing_or_invalid_third_confirmation_never_activates(ack_kind):
    rig = Rig()
    rig.double()
    rig.double()
    rig.double(ack=False)
    request = rig.model.pending_mode_request
    if ack_kind == 'wrong_ticket':
        rig.send(ack=request.ticket + 1, mode=Mode.SPORT)
    elif ack_kind == 'wrong_mode':
        rig.confirm(mode=Mode.DRIVE)
    elif ack_kind == 'timeout':
        rig.send(delay=501, ack=request.ticket, mode=Mode.SPORT)
    else:
        rig.wait(1000, mode=Mode.SPORT)
    assert rig.model.state is State.NORMAL
    assert Action.ACTIVATE not in rig.actions


@pytest.mark.parametrize('which', [0, 1])
def test_uncompleted_first_two_stock_actions_invalidate_sequence(which):
    rig = Rig()
    for index in range(3):
        rig.double(ack=index != which)
    assert rig.model.state is State.NORMAL
    assert Action.ACTIVATE not in rig.actions
    assert rig.actions.count(Action.NEXT_MODE) == 3


@pytest.mark.parametrize('event,action', [(1, Action.LIGHT), (3, Action.LONG_PRESS),
    (4, Action.OEM_EVENT), (5, Action.OEM_EVENT), (6, Action.OEM_EVENT),
    (7, Action.OEM_EVENT), (255, Action.OEM_EVENT)])
@pytest.mark.parametrize('active', [False, True])
def test_single_long_reset_and_other_oem_events_are_forwarded(event, action, active):
    rig = Rig()
    if active:
        rig.activate()
    rig.send(event)
    assert rig.actions == [action]
    assert rig.model.state is (State.ACTIVE if active else State.NORMAL)


@pytest.mark.parametrize('event', [1, 3, 4, 5, 6, 7, 255])
def test_non_double_events_interrupt_activation_without_being_swallowed(event):
    rig = Rig()
    rig.double()
    rig.double()
    rig.send(event)
    rig.double()
    assert Action.ACTIVATE not in rig.actions
    assert rig.model.double_count == 1


def test_dense_six_click_original_trace_is_not_reinterpreted_as_ssm():
    rig = Rig()
    for offset, event in [(250, 2), (570, 2), (730, 5), (890, 2)]:
        rig.send(event, delay=offset - (rig.now - 600))
        if event == 2:
            rig.confirm()
    assert Action.ACTIVATE not in rig.actions
    assert Action.OEM_EVENT in rig.actions
    assert rig.actions.count(Action.NEXT_MODE) == 3
    assert rig.model.double_count == 1


@pytest.mark.parametrize('gap,valid', [(599, False), (600, True), (1600, True), (1601, False)])
def test_double_interval_boundaries(gap, valid):
    rig = Rig()
    for index in range(3):
        rig.send(2, delay=10 if index == 0 else gap - 10)
        rig.confirm()
    assert (Action.ACTIVATE in rig.actions) is valid


def test_total_sequence_window_is_independent_of_pair_gap():
    rig = Rig(timing=Timing(double_min_ms=600, double_gap_ms=1600, sequence_ms=2000))
    for _ in range(3):
        rig.double(delay=1100)
    assert Action.ACTIVATE not in rig.actions


@pytest.mark.parametrize('changes', [
    {'powered': False}, {'mode': None}, {'mode': 'sport'},
    {'speed_mm_s': 1}, {'speed_mm_s': -1}, {'speed_mm_s': None},
    {'speed_mm_s': False}, {'fault': True}, {'fault': None},
    {'throttle_released': False}, {'throttle_released': None},
    {'locked': True}, {'locked': None}, {'telemetry_valid': False},
    {'oem_reserved': True}, {'oem_reserved': None},
])
def test_all_activation_guards_are_explicit(changes):
    rig = Rig(inputs=replace(READY, **changes))
    for _ in range(3):
        result = rig.double(ack=False)
        if Action.NEXT_MODE in result and rig.model.pending_mode_request:
            rig.confirm()
    assert rig.model.state is State.NORMAL
    assert Action.ACTIVATE not in rig.actions


def test_disabled_by_default_keeps_normal_mode_actions():
    assert not SuperSportSimulation().enabled
    rig = Rig(enabled=False)
    for _ in range(3):
        rig.double()
    assert rig.actions == [Action.NEXT_MODE] * 3
    assert rig.model.state is State.NORMAL


@pytest.mark.parametrize('changes', [
    {'speed_mm_s': 1}, {'throttle_released': False}, {'fault': True},
    {'locked': True}, {'telemetry_valid': False}, {'oem_reserved': True},
])
def test_unsafe_interval_clears_whole_partial_sequence(changes):
    rig = Rig()
    rig.double()
    rig.double()
    rig.send(**changes)
    rig.wait(600, **{key: getattr(READY, key) for key in changes})
    rig.double()
    assert Action.ACTIVATE not in rig.actions
    assert rig.model.double_count == 1


@pytest.mark.parametrize('kind', ['fault', 'throttle', 'dashboard', 'single'])
def test_safety_or_oem_event_wins_over_simultaneous_third_ack(kind):
    rig = Rig()
    rig.double()
    rig.double()
    rig.double(ack=False)
    request = rig.model.pending_mode_request
    changes = {'fault': True} if kind == 'fault' else {'throttle_released': False} if kind == 'throttle' else {}
    rig.send(1 if kind == 'single' else None, ack=request.ticket,
             mode=Mode.SPORT, dashboard=kind == 'dashboard', **changes)
    assert Action.ACTIVATE not in rig.actions
    if kind == 'single':
        assert rig.actions[-1] is Action.LIGHT


def test_standstill_dwell_is_required_before_first_double():
    rig = Rig(inputs=replace(READY, speed_mm_s=1))
    rig.send(speed_mm_s=0)
    rig.send(2, delay=100)
    rig.confirm()
    rig.double()
    rig.double()
    assert Action.ACTIVATE not in rig.actions


@pytest.mark.parametrize('mode', list(Mode))
def test_normal_double_delegates_original_and_waits_for_ack(mode):
    rig = Rig(inputs=replace(READY, mode=mode))
    assert rig.double(ack=False) == [Action.NEXT_MODE]
    assert rig.model.inputs.mode is mode
    assert rig.model.pending_mode_request.target is next_stock_mode(mode)
    rig.confirm()
    assert rig.model.inputs.mode is next_stock_mode(mode)


def test_one_double_deactivates_to_original_sport_limit_without_mode_cycle():
    rig = Rig()
    rig.activate()
    rig.double()
    assert rig.actions == [Action.DEACTIVATE]
    assert rig.model.inputs.mode is Mode.SPORT
    assert rig.model.speed_override_kmh is None
    assert rig.model.pending_mode_request is None
    assert rig.model.double_count == 0


def test_moving_exit_is_deferred_and_never_commands_braking():
    rig = Rig()
    rig.activate()
    rig.send(speed_mm_s=8333, throttle_released=False)
    rig.double()
    assert rig.actions == [Action.DEFER_EXIT]
    assert rig.model.state is State.EXIT_PENDING
    assert rig.model.speed_override_kmh == 30
    rig.wait(400, speed_mm_s=0, throttle_released=True)
    assert rig.model.state is State.EXIT_PENDING
    rig.wait(200)
    assert rig.actions == [Action.DEFER_EXIT, Action.DEACTIVATE]
    assert rig.model.inputs.mode is Mode.SPORT


@pytest.mark.parametrize('changes', [
    {'fault': True}, {'fault': None}, {'telemetry_valid': False},
    {'locked': True}, {'mode': Mode.DRIVE}, {'speed_mm_s': None},
    {'oem_reserved': True},
])
def test_fault_and_uncertainty_latch_exit_with_original_safety_priority(changes):
    rig = Rig()
    rig.activate()
    rig.send(speed_mm_s=5000)
    rig.send(**changes)
    assert rig.model.state is State.EXIT_PENDING
    assert rig.actions == [Action.DEFER_EXIT]
    rig.wait(20, **{key: getattr(READY, key) for key in changes})
    rig.wait(600, speed_mm_s=0)
    assert rig.model.state is State.NORMAL
    assert rig.actions[-1] is Action.DEACTIVATE
    assert Action.NEXT_MODE not in rig.actions


def test_changed_drive_mode_requires_sport_restoration_before_exit_completes():
    rig = Rig()
    rig.activate()
    rig.send(mode=Mode.DRIVE)
    assert rig.model.state is State.EXIT_PENDING
    assert rig.actions == [Action.DEFER_EXIT, Action.RESTORE_SPORT]
    rig.confirm()
    assert rig.model.state is State.NORMAL
    assert rig.model.inputs.mode is Mode.SPORT
    assert rig.actions[-1] is Action.DEACTIVATE


def test_reserved_oem_double_is_never_consumed_for_ssm_exit():
    rig = Rig()
    rig.activate()
    rig.send(2, oem_reserved=True)
    assert Action.OEM_EVENT in rig.actions
    assert Action.NEXT_MODE not in rig.actions


def test_double_on_same_sample_as_deferred_exit_cannot_cycle_or_reactivate():
    rig = Rig()
    rig.activate()
    rig.send(speed_mm_s=5000)
    rig.double()
    rig.wait(500, speed_mm_s=0)
    rig.send(2, delay=20)
    assert rig.model.state is State.NORMAL
    assert rig.actions[-1] is Action.DEACTIVATE
    assert Action.NEXT_MODE not in rig.actions


def test_restart_and_power_cycle_discard_active_and_partial_states():
    rig = Rig()
    rig.activate()
    rig.model.reset()
    assert rig.model.state is State.NORMAL
    assert rig.model.speed_override_kmh is None
    assert rig.model.pending_mode_request is None
    assert rig.model.double_count == 0
    assert rig.model.display({})['mode_icons'] == frozenset()
    assert rig.model.sample(0, None, READY) == []
    rig = Rig()
    rig.double()
    rig.send(powered=False)
    rig.wait(600, powered=True)
    rig.double()
    rig.double()
    assert Action.ACTIVATE not in rig.actions


def test_old_ticket_cannot_be_reused_after_reset():
    rig = Rig()
    rig.double(ack=False)
    old = rig.model.pending_mode_request.ticket
    rig.model.reset()
    rig.model.sample(0, None, READY)
    rig.model.sample(600, None, READY)
    rig.model.sample(610, 2, READY)
    assert rig.model.pending_mode_request.ticket != old
    assert rig.model.sample(620, None, replace(READY, mode=Mode.WALK), mode_ack=old) == []
    assert rig.model.double_count == 0


@pytest.mark.parametrize('mode', list(Mode))
def test_display_keeps_other_fields_and_steady_three_icons(mode):
    rig = Rig(inputs=replace(READY, mode=mode))
    frame = {'speed': 17, 'battery': 57, 'light': True, 'bluetooth': True,
             'warnings': ('temperature',), 'error': 42, 'unknown': b'abc',
             'mode_icons': 'original'}
    assert rig.model.display(frame)['mode_icons'] == frozenset((mode,))
    rig.send(mode=Mode.SPORT)
    rig.activate()
    for _ in range(20):
        output = rig.model.display(frame)
        assert output['mode_icons'] == frozenset(Mode)
        assert {k: v for k, v in output.items() if k != 'mode_icons'} == {
            k: v for k, v in frame.items() if k != 'mode_icons'
        }
        rig.wait(100)
    assert frame['mode_icons'] == 'original'
    rig.double()
    assert rig.model.display(frame)['mode_icons'] == frozenset((Mode.SPORT,))


@pytest.mark.parametrize('bad', [-1, 0, 1.5, True])
def test_invalid_time_does_not_mutate_active_state(bad):
    rig = Rig()
    rig.activate()
    with pytest.raises(ValueError):
        rig.model.sample(bad, None, Inputs())
    assert rig.model.state is State.ACTIVE
    assert rig.model.inputs == READY


@pytest.mark.parametrize('bad', [True, False, -1, 256, 1.5, '2'])
def test_raw_button_levels_and_invalid_oem_codes_are_rejected(bad):
    rig = Rig()
    with pytest.raises(ValueError):
        rig.model.sample(rig.now + 1, bad, READY)
    assert rig.model.inputs == READY


@pytest.mark.parametrize('bad', [True, 0, -1, '3'])
def test_invalid_ack_does_not_mutate_state(bad):
    rig = Rig()
    with pytest.raises(ValueError):
        rig.model.sample(rig.now + 1, None, READY, mode_ack=bad)
    assert rig.model.double_count == 0


def test_duplicate_event_timestamp_is_not_counted_or_forwarded_twice():
    rig = Rig()
    rig.send(2)
    rig.send(2, delay=0)
    assert rig.actions == [Action.NEXT_MODE, Action.REJECT]
    assert rig.model.double_count == 0


@pytest.mark.parametrize('kwargs', [
    {'double_min_ms': 0}, {'double_gap_ms': 600}, {'standstill_ms': -1},
    {'sequence_ms': 1600}, {'confirm_ms': 1600}, {'confirm_ms': True},
])
def test_invalid_timing_is_rejected(kwargs):
    with pytest.raises(ValueError):
        Timing(**kwargs)


def test_random_oem_events_while_moving_never_activate():
    rng = random.Random(1527)
    model = SuperSportSimulation(enabled=True)
    for now in range(0, 60000, 10):
        event = rng.choice([None, 1, 2, 3, 5, 6, 7]) if rng.random() < 0.12 else None
        actions = model.sample(now, event, replace(READY, speed_mm_s=rng.randint(1, 9000)))
        assert Action.ACTIVATE not in actions
        assert model.state is State.NORMAL
