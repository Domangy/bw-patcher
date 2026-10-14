#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Ereignisdemo mit ausdrücklich simulierten OEM-Modusquittungen."""

from dataclasses import replace
import json

from bwpatcher.ssm import Action, Inputs, Mode, SuperSportSimulation, next_stock_mode


def demonstration() -> list[dict]:
    model = SuperSportSimulation(enabled=True)
    inputs = Inputs(
        powered=True, mode=Mode.SPORT, speed_mm_s=0, fault=False,
        throttle_released=True, locked=False, telemetry_valid=True, oem_reserved=False,
    )
    trace = []
    now = 0

    def sample(event=None, *, ack=None):
        actions = model.sample(now, event, inputs, mode_ack=ack)
        if actions or ack is not None:
            trace.append({
                'time_ms': now, 'actions': [a.value for a in actions],
                'state': model.state.value, 'confirmed_mode': inputs.mode.value,
                'speed_override_kmh': model.speed_override_kmh,
                'mode_icons': sorted(m.value for m in model.display({})['mode_icons']),
                'ack_source': 'simulierter OEM-Abschluss' if ack is not None else None,
            })
        return actions

    def wait(duration):
        nonlocal now
        for _ in range(duration // 10):
            now += 10
            sample()

    def double():
        nonlocal inputs
        wait(920)
        actions = sample(2)
        if Action.NEXT_MODE in actions:
            request = model.pending_mode_request
            # Nur dieser Demo-Adapter simuliert den Originalabschluss.
            inputs = replace(inputs, mode=next_stock_mode(inputs.mode))
            wait(10)
            sample(ack=request.ticket)

    sample()
    wait(600)
    for _ in range(3):
        double()
    inputs = replace(inputs, speed_mm_s=8000, throttle_released=False)
    wait(100)
    double()
    inputs = replace(inputs, speed_mm_s=0, throttle_released=True)
    wait(600)
    for _ in range(3):
        double()
    model.reset()
    trace.append({
        'event': 'Neustart', 'state': model.state.value,
        'speed_override_kmh': model.speed_override_kmh,
        'mode_icons': sorted(m.value for m in model.display({})['mode_icons']),
    })
    return trace


def main():
    print(json.dumps({
        'status': 'Nur Ereignissimulation mit simulierten Quittungen; kein Firmware-Patch',
        'trace': demonstration(),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
