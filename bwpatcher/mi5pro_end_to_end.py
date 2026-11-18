"""Belegbarer BLE/OEM-Klick -> MCU-Moduspfad, ausschliesslich offline.

Keine Codeinjektion, keine echte Benutzer-Absichtsfreigabe,
keine Hardwarequittung, kein Flash- oder Geschwindigkeits-Patch.
"""
from dataclasses import replace
import argparse
import json
from pathlib import Path

from bwpatcher.mi5pro_emulator import OriginalAppEmulator
from bwpatcher.mi5pro_integration import McuOriginal, require_original
from bwpatcher.mi5pro_research import AnalysisError, inspect_ble
from bwpatcher.ssm import Action, Inputs, Mode, SuperSportSimulation

MODE_FROM_OEM = {11: Mode.WALK, 2: Mode.DRIVE, 3: Mode.SPORT}


def emulate_full_chain(ble: bytes, mcu: bytes, *, demo_intent=False) -> dict:
    """Nachweis mit originalen Routinen und synthetischen Telemetrie-Snapshots.

    Die Modell-Tickets werden hier ausschliesslich synthetisch quittiert.
    Es wurde KEINE Quittung des wirklich angewendeten Motorlimits nachgewiesen.
    """
    if type(demo_intent) is not bool:
        raise TypeError("demo_intent muss bool sein.")
    require_original(ble, "ble")
    require_original(mcu, "mcu")
    app = inspect_ble(ble).app

    dashboard = OriginalAppEmulator(app)
    dashboard.uc.mem_write(dashboard.INFO + 1, b"\x03")
    dashboard.uc.mem_write(dashboard.INFO + 0xE, b"\x01")
    trace = dashboard.click_trace(6, pair_pause_ticks=60, dispatch=True)
    if (len(trace) != 3
            or [e["event"] for e in trace] != [2, 2, 2]
            or [e["mode_after"] for e in trace] != [11, 2, 3]
            or [e["tick"] for e in trace] != [25, 117, 209]
            or not all(e["mode_cycle_called"] for e in trace)):
        raise AnalysisError("Originaler Dreifach-Doppelklick-Trace ungueltig.")

    inputs = Inputs(
        powered=True, mode=Mode.SPORT, speed_mm_s=0, fault=False,
        throttle_released=True, locked=False, telemetry_valid=True,
        oem_reserved=False,
    )
    model = SuperSportSimulation(enabled=True)
    model.sample(0, None, inputs)
    model.sample(600, None, inputs)
    if demo_intent:
        if not model.grant_activation_intent(600):
            raise AnalysisError("Synthetische Absichtsfreigabe abgewiesen.")

    ble_tx = OriginalAppEmulator(app)
    mcu_rx = McuOriginal(mcu)
    limits = mcu_rx.select_limits(b"60556")  # reiner Test-Seriennummernpraefix
    path = []
    for e in trace:
        now = 600 + e["nominal_ms"]
        actions = model.sample(now, e["event"], inputs)
        request = model.pending_mode_request
        mode = MODE_FROM_OEM[e["mode_after"]]
        if Action.NEXT_MODE not in actions or request is None or request.target is not mode:
            raise AnalysisError("SSM-Zustandsmodell und OEM-Modusentscheidung widersprechen sich.")
        frame = ble_tx.controller_frame(e["mode_after"], 2)
        mcu_rx.consume_mode(frame)
        observed = mcu_rx.read(0x20000229, 1)[0]
        if observed != e["mode_after"]:
            raise AnalysisError("MCU hat den originalen Modus nicht uebernommen.")
        original_limit = mcu_rx.speed_selection(observed)
        inputs = replace(inputs, mode=mode)
        follow = model.sample(now + 10, None, inputs, mode_ack=request.ticket)
        path.append({
            "time_ms_synthetic": now,
            "oem_event": e["event"],
            "dashboard_mode": e["mode_after"],
            "ble_frame": frame.hex(),
            "mcu_mode": observed,
            "selected_original_limit_raw": original_limit,
            "model_ack": True,
            "model_actions": [x.value for x in follow],
        })
    return {
        "scope": "Unicorn-Emulation von OEM-BLE und OEM-MCU, keine Hardware",
        "three_distinct_doubles_verified": True,
        "independent_intent_only_simulated": demo_intent,
        "model_state": model.state.value,
        "model_request_kmh": model.speed_override_kmh,
        "original_drive_limit_raw": limits["drive_raw"],
        "original_sport_limit_raw": limits["sport_raw"],
        "final_original_limit_raw": path[-1]["selected_original_limit_raw"],
        "real_applied_30_kmh_proven": False,
        "real_limit_acknowledgement_proven": False,
        "ssm_firmware_created": False,
        "flashable": False,
        "path": path,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ble", type=Path, required=True)
    parser.add_argument("--mcu", type=Path, required=True)
    parser.add_argument("--demo-intent", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(emulate_full_chain(
        args.ble.read_bytes(), args.mcu.read_bytes(), demo_intent=args.demo_intent,
    ), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
