#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Modelltests mit synthetischen Pegeln, ausdrücklich keine Hardwaretests."""

from dataclasses import replace
import random

import pytest

from bwpatcher.ssm import (
    Action, ButtonRecognizer, Gesture, Inputs, Mode, State,
    SuperSportSimulation, Timing, next_stock_mode,
)


READY = Inputs(
    powered=True, mode=Mode.SPORT, speed_mm_s=0, fault=False,
    throttle_released=True, locked=False, telemetry_valid=True,
)


class Rig:
    def __init__(self, *, enabled=True, inputs=READY):
        self.model = SuperSportSimulation(enabled=enabled)
        self.inputs = inputs
        self.now = 0
        self.pressed = False
        self.actions = []
        self.actions.extend(self.model.sample(0, False, self.inputs))
        self.hold(False, 600)

    def hold(self, pressed, duration, **changes):
        self.inputs = replace(self.inputs, **changes)
        self.pressed = pressed
        for _ in range(duration // 10):
            self.now += 10
            self.actions.extend(self.model.sample(self.now, pressed, self.inputs))

    def clicks(self, count, *, finish=True, press=80, pause=80):
        for _ in range(count):
            self.hold(True, press)
            self.hold(False, pause)
        if finish:
            self.hold(False, 400)

    def activate(self):
        self.clicks(5)
        assert self.model.state is State.ACTIVE
        self.actions.clear()


@pytest.mark.parametrize("count,action", [
    (1, Action.LIGHT), (2, Action.NEXT_MODE), (3, Action.REJECT),
    (4, Action.REJECT), (5, Action.ACTIVATE), (6, Action.REJECT),
])
def test_exact_click_count(count, action):
    rig = Rig()
    rig.clicks(count)
    assert rig.actions == [action]
    assert (rig.model.state is State.ACTIVE) == (count == 5)


def test_first_two_clicks_do_not_change_mode_before_five():
    rig = Rig()
    rig.clicks(2, finish=False)
    assert rig.actions == []
    rig.clicks(3)
    assert rig.actions == [Action.ACTIVATE]


def test_fifth_click_waits_for_sixth_click_window():
    rig = Rig()
    rig.clicks(5, finish=False)
    assert rig.model.state is State.NORMAL
    rig.clicks(1)
    assert rig.model.state is State.NORMAL
    assert rig.actions == [Action.REJECT]


def test_new_press_during_debounce_never_commits_a_double():
    rig = Rig()
    rig.clicks(2, finish=False)
    # Letztes Loslassen stabil bei now-40; neuer Druck 10 ms vor Frist.
    rig.hold(False, 290)
    rig.clicks(3)
    assert rig.actions == [Action.ACTIVATE]


def test_slow_clicks_are_independent_single_clicks():
    rig = Rig()
    for _ in range(5):
        rig.clicks(1)
    assert rig.actions == [Action.LIGHT] * 5


def test_electrical_bounce_does_not_create_clicks():
    rig = Rig()
    for _ in range(5):
        for _ in range(3):
            rig.hold(True, 10)
            rig.hold(False, 10)
        rig.hold(True, 80)
        for _ in range(3):
            rig.hold(False, 10)
            rig.hold(True, 10)
        rig.hold(False, 80)
    rig.hold(False, 400)
    assert rig.actions == [Action.ACTIVATE]


def test_pulses_shorter_than_debounce_are_ignored():
    rig = Rig()
    for _ in range(30):
        rig.hold(True, 20)
        rig.hold(False, 20)
    rig.hold(False, 400)
    assert rig.actions == []


def test_long_press_cancels_partial_sequence_and_fires_once():
    rig = Rig()
    rig.clicks(2, finish=False)
    rig.hold(True, 2500)
    rig.hold(False, 500)
    assert rig.actions == [Action.LONG_PRESS]
    assert rig.model.state is State.NORMAL


def test_overlong_sequence_is_discarded():
    rig = Rig()
    rig.clicks(5, press=300, pause=250)
    assert Action.ACTIVATE not in rig.actions
    assert Action.NEXT_MODE not in rig.actions


@pytest.mark.parametrize("changes", [
    {"powered": False}, {"mode": Mode.WALK}, {"mode": Mode.DRIVE},
    {"speed_mm_s": 1}, {"speed_mm_s": -1}, {"speed_mm_s": None},
    {"speed_mm_s": False}, {"fault": True}, {"fault": None},
    {"throttle_released": False}, {"throttle_released": None},
    {"locked": True}, {"locked": None}, {"telemetry_valid": False},
])
def test_activation_requires_all_conditions(changes):
    rig = Rig(inputs=replace(READY, **changes))
    rig.clicks(5)
    assert rig.model.state is State.NORMAL
    assert Action.ACTIVATE not in rig.actions


def test_disabled_by_default():
    assert SuperSportSimulation().enabled is False
    rig = Rig(enabled=False)
    rig.clicks(5)
    assert rig.actions == [Action.REJECT]


@pytest.mark.parametrize("changes", [
    {"speed_mm_s": 1}, {"throttle_released": False},
    {"fault": True}, {"mode": Mode.DRIVE}, {"locked": True},
    {"telemetry_valid": False},
])
def test_loss_of_eligibility_cannot_be_rearmed_mid_sequence(changes):
    rig = Rig()
    rig.clicks(2, finish=False)
    rig.hold(False, 10, **changes)
    rig.hold(False, 10, **{k: getattr(READY, k) for k in changes})
    rig.clicks(3)
    assert Action.ACTIVATE not in rig.actions


def test_stationary_dwell_required_at_start_of_sequence():
    rig = Rig(inputs=replace(READY, speed_mm_s=1))
    rig.hold(False, 10, speed_mm_s=0)
    rig.clicks(5)
    assert rig.actions == [Action.REJECT]


def test_dashboard_event_has_priority_over_expiring_activation():
    rig = Rig()
    rig.clicks(5, finish=False)
    rig.now += 400
    rig.actions.extend(rig.model.sample(rig.now, False, READY, dashboard_event=True))
    rig.hold(False, 500)
    assert Action.ACTIVATE not in rig.actions


@pytest.mark.parametrize("mode,target", [
    (Mode.WALK, Mode.DRIVE), (Mode.DRIVE, Mode.SPORT), (Mode.SPORT, Mode.WALK),
])
def test_stock_mode_order_and_original_handoff(mode, target):
    rig = Rig(inputs=replace(READY, mode=mode))
    rig.clicks(2)
    assert rig.actions == [Action.NEXT_MODE]
    assert rig.model.inputs.mode is mode  # Originalfirmware bestätigt erst danach.
    assert next_stock_mode(mode) is target
    rig.hold(False, 10, mode=target)
    assert rig.model.display({})["mode_icons"] == frozenset((target,))


def test_deactivation_returns_to_sport_without_cycling():
    rig = Rig()
    rig.activate()
    rig.clicks(2)
    assert rig.actions == [Action.DEACTIVATE]
    assert rig.model.inputs.mode is Mode.SPORT
    assert rig.model.speed_override_kmh is None


def test_deactivation_while_moving_is_deferred_until_stable_standstill():
    rig = Rig()
    rig.activate()
    rig.hold(False, 10, speed_mm_s=8333, throttle_released=False)
    rig.clicks(2)
    assert rig.actions == [Action.DEFER_EXIT]
    assert rig.model.state is State.EXIT_PENDING
    assert rig.model.speed_override_kmh == 30
    rig.hold(False, 400, speed_mm_s=0)
    assert rig.model.state is State.EXIT_PENDING
    rig.hold(False, 200)
    assert rig.model.state is State.NORMAL
    assert rig.actions == [Action.DEFER_EXIT, Action.DEACTIVATE]


@pytest.mark.parametrize("changes", [
    {"fault": True}, {"fault": None}, {"telemetry_valid": False},
    {"locked": True}, {"mode": Mode.DRIVE}, {"speed_mm_s": None},
])
def test_faults_latch_exit_without_introducing_brake_commands(changes):
    rig = Rig()
    rig.activate()
    rig.hold(False, 10, speed_mm_s=5000)
    rig.hold(False, 10, **changes)
    assert rig.actions == [Action.DEFER_EXIT]
    rig.hold(False, 20, **{k: getattr(READY, k) for k in changes})
    assert rig.model.state is State.EXIT_PENDING
    rig.hold(False, 600, speed_mm_s=0)
    assert rig.model.state is State.NORMAL
    assert rig.actions == [Action.DEFER_EXIT, Action.DEACTIVATE]


def test_fault_at_standstill_removes_ssm_immediately():
    rig = Rig()
    rig.activate()
    rig.hold(False, 10, fault=True)
    assert rig.model.state is State.NORMAL
    assert rig.actions == [Action.DEFER_EXIT, Action.DEACTIVATE]


@pytest.mark.parametrize("count", [2, 5])
def test_gesture_crossing_deferred_exit_cannot_cycle_or_reactivate(count):
    rig = Rig()
    rig.activate()
    rig.hold(False, 10, speed_mm_s=5000)
    rig.clicks(2)
    assert rig.model.state is State.EXIT_PENDING
    rig.hold(False, 400, speed_mm_s=0)
    rig.actions.clear()
    # Die erste Druckflanke liegt vor der Stillstandsbestätigung, das Ende
    # der Folge danach. Ihr Ursprung muss über den Zustandswechsel erhalten bleiben.
    rig.clicks(count)
    assert rig.model.state is State.NORMAL
    assert Action.DEACTIVATE in rig.actions
    assert Action.NEXT_MODE not in rig.actions
    assert Action.ACTIVATE not in rig.actions


def test_light_and_long_press_remain_original_actions_in_ssm():
    rig = Rig()
    rig.activate()
    rig.clicks(1)
    rig.hold(True, 2000)
    assert rig.actions == [Action.LIGHT, Action.LONG_PRESS]
    rig.hold(False, 500, powered=False)
    rig.hold(False, 600, powered=True)
    assert rig.model.state is State.NORMAL


def test_reset_discards_ssm_pending_exit_and_partial_gesture():
    rig = Rig()
    rig.activate()
    rig.clicks(2, finish=False)
    rig.model.reset()
    assert rig.model.speed_override_kmh is None
    assert rig.model.buttons.count == 0
    assert rig.model.state is State.NORMAL
    assert rig.model.display({})["mode_icons"] == frozenset((Mode.SPORT,))
    # Eine zurückgesetzte monotone Uhr ist nach reset zulässig.
    assert rig.model.sample(0, False, READY) == []


@pytest.mark.parametrize("mode", list(Mode))
def test_display_preserves_every_other_field(mode):
    rig = Rig(inputs=replace(READY, mode=mode))
    frame = {
        "speed": 17, "battery": 57, "light": True, "bluetooth": True,
        "warnings": ("temperature",), "error": 42, "unknown_vendor_field": b"abc",
        "mode_icons": "original",
    }
    normal = rig.model.display(frame)
    assert normal["mode_icons"] == frozenset((mode,))
    rig.hold(False, 600, mode=Mode.SPORT)
    rig.activate()
    for _ in range(20):
        active = rig.model.display(frame)
        assert active["mode_icons"] == frozenset(Mode)
        assert {k: v for k, v in active.items() if k != "mode_icons"} == {
            k: v for k, v in frame.items() if k != "mode_icons"
        }
        rig.hold(False, 100)
    assert frame["mode_icons"] == "original"
    rig.clicks(2)
    assert rig.model.display(frame)["mode_icons"] == frozenset((Mode.SPORT,))
    rig.model.reset()
    assert rig.model.display(frame)["mode_icons"] == frozenset((Mode.SPORT,))


def test_invalid_and_backward_time_does_not_mutate_model():
    rig = Rig()
    rig.activate()
    for invalid in (-1, 0, 1.5, True):
        with pytest.raises(ValueError):
            rig.model.sample(invalid, False, Inputs())
        assert rig.model.state is State.ACTIVE
        assert rig.model.inputs == READY


def test_conflicting_same_timestamp_button_levels_cancel_sequence():
    rig = Rig()
    rig.clicks(5, finish=False)
    rig.model.sample(rig.now, True, READY)
    rig.model.sample(rig.now, False, READY)
    rig.hold(False, 500)
    assert Action.ACTIVATE not in rig.actions


@pytest.mark.parametrize("kwargs", [
    {"debounce_ms": 0}, {"gap_ms": 20}, {"long_ms": 20},
    {"standstill_ms": -1}, {"sequence_ms": 400}, {"long_ms": True},
])
def test_invalid_timing_rejected(kwargs):
    with pytest.raises(ValueError):
        Timing(**kwargs)


def test_gap_boundary_is_deterministic():
    button = ButtonRecognizer()
    assert button.update(0, True) == []
    assert button.update(30, True) == [Gesture.START]
    button.update(80, False)
    button.update(110, False)
    assert button.update(459, False) == []
    assert button.update(460, True) == [Gesture.SINGLE]
    assert button.update(490, True) == [Gesture.START]


def test_randomized_motion_never_activates_ssm():
    rng = random.Random(1527)
    model = SuperSportSimulation(enabled=True)
    pressed = False
    for now in range(0, 60000, 10):
        if rng.random() < 0.12:
            pressed = not pressed
        actions = model.sample(now, pressed, replace(READY, speed_mm_s=rng.randint(1, 9000)))
        assert Action.ACTIVATE not in actions
        assert model.state is State.NORMAL


def test_rejected_sequence_does_not_poison_next_complete_sequence():
    rig = Rig()
    rig.clicks(6)
    rig.actions.clear()
    rig.clicks(5)
    assert rig.actions == [Action.ACTIVATE]
