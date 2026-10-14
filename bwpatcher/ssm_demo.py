#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Deterministische Offline-Demo: python -m bwpatcher.ssm_demo."""

from dataclasses import replace
import json

from bwpatcher.ssm import Inputs, Mode, SuperSportSimulation


def demonstration() -> list[dict]:
    model = SuperSportSimulation(enabled=True)
    inputs = Inputs(
        powered=True, mode=Mode.SPORT, speed_mm_s=0, fault=False,
        throttle_released=True, locked=False, telemetry_valid=True,
    )
    trace = []
    now = 0

    def sample(pressed, duration):
        nonlocal now
        for _ in range(duration // 10):
            now += 10
            actions = model.sample(now, pressed, inputs)
            if actions:
                trace.append({
                    "time_ms": now,
                    "actions": [a.value for a in actions],
                    "state": model.state.value,
                    "speed_override_kmh": model.speed_override_kmh,
                    "mode_icons": sorted(m.value for m in model.display({})["mode_icons"]),
                })

    def clicks(count):
        for _ in range(count):
            sample(True, 80)
            sample(False, 80)
        sample(False, 400)

    sample(False, 600)
    clicks(5)
    inputs = replace(inputs, speed_mm_s=8000, throttle_released=False)
    sample(False, 100)
    clicks(2)
    inputs = replace(inputs, speed_mm_s=0, throttle_released=True)
    sample(False, 600)
    clicks(5)
    model.reset()
    trace.append({
        "event": "Neustart", "state": model.state.value,
        "speed_override_kmh": model.speed_override_kmh,
        "mode_icons": sorted(m.value for m in model.display({})["mode_icons"]),
    })
    return trace


def main():
    print(json.dumps({
        "status": "Nur Simulation, kein Firmware-Patch oder Hardwaretest",
        "trace": demonstration(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
