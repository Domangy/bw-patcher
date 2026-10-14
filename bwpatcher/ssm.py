#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""SSM-Ereignisspezifikation, ohne Roh-Tastenparser oder Gerätezugriff.

Eingaben sind unveränderte OEM-Ereigniscodes. Der Adapter muss Originalaktionen
und deren tatsächlichen Abschluss bestätigen; ein Sollmodus ist keine Quittung.
Zeitfenster sind Entwurfswerte, keine Messungen am Xiaomi-Dashboard.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


SSM_STATUS = "Simulation vorhanden · Firmware-Patch nicht verfügbar · Hardware ungeprüft"
SSM_BLOCK_REASON = (
    "SSM ist ausschliesslich als Offline-Simulation implementiert. "
    "Eine sichere Integration der Originalereignisse, Schutzfunktionen und Anzeige fehlt; "
    "es wird keine SSM-Firmware erzeugt. Auch --experimental hebt dies nicht auf."
)


class SSMUnavailableError(ValueError):
    """SSM darf nicht als Firmware-Patch exportiert werden."""


class Mode(str, Enum):
    WALK = "walk"
    DRIVE = "drive"
    SPORT = "sport"


class State(str, Enum):
    NORMAL = "normal"
    ACTIVE = "active"
    EXIT_PENDING = "exit_pending"


class Action(str, Enum):
    # OEM-Aktionen sind Übergaben an die Originalentscheidung samt deren Prüfungen.
    LIGHT = "original_light_toggle"
    NEXT_MODE = "original_next_mode"
    LONG_PRESS = "original_long_press"
    OEM_EVENT = "original_event_passthrough"
    RESTORE_SPORT = "original_restore_sport_requested"
    ACTIVATE = "ssm_activate"
    DEACTIVATE = "ssm_deactivate"
    DEFER_EXIT = "ssm_exit_at_standstill"
    REJECT = "sequence_rejected"


@dataclass(frozen=True)
class Timing:
    double_min_ms: int = 600
    double_gap_ms: int = 1600
    sequence_ms: int = 4000
    confirm_ms: int = 500
    standstill_ms: int = 500

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in vars(self).values()):
            raise ValueError("Zeiten müssen positive ganze Millisekunden sein.")
        if not self.double_min_ms < self.double_gap_ms < self.sequence_ms:
            raise ValueError("Mindestabstand < Doppelabstand < Sequenzdauer erforderlich.")
        if self.confirm_ms >= self.double_gap_ms:
            raise ValueError("Bestätigungsfrist muss kleiner als der Doppelabstand sein.")


@dataclass(frozen=True)
class Inputs:
    # None ist unbekannt und gibt SSM niemals frei.
    powered: bool = False
    mode: Mode | None = None
    speed_mm_s: int | None = None
    fault: bool | None = None
    throttle_released: bool | None = None
    locked: bool | None = None
    telemetry_valid: bool = False
    oem_reserved: bool | None = None

    @property
    def stopped(self) -> bool:
        return (
            self.telemetry_valid is True
            and type(self.speed_mm_s) is int and self.speed_mm_s == 0
        )

    @property
    def activation_safe(self) -> bool:
        # Während der ersten beiden OEM-Moduswechsel ist Sport nicht erforderlich.
        return (
            self.powered is True and isinstance(self.mode, Mode) and self.stopped
            and self.fault is False and self.throttle_released is True
            and self.locked is False and self.oem_reserved is False
        )


@dataclass(frozen=True)
class ModeRequest:
    ticket: int
    target: Mode
    issued_at: int
    activate_after: bool = False
    restore: bool = False


class SuperSportSimulation:
    """Zählt drei getrennte OEM-Doppelklicks (Code 2), ohne Rohabtastung.

    sample() nimmt pro Aufruf höchstens ein einmalig zugestelltes OEM-Ereignis.
    Code 0/None bedeutet keine Taste. mode_ack quittiert einen zuvor ausgegebenen
    ModeRequest anhand tatsächlicher Telemetrie nach der Originalaktion.
    Keine Aktion ist ein Motor-, Brems-, NVM- oder Flashbefehl.
    """

    def __init__(self, *, enabled: bool = False, timing: Timing = Timing()):
        self.enabled = enabled
        self.timing = timing
        self._serial = 0
        self.reset()

    def reset(self):
        self.state = State.NORMAL
        self.inputs = Inputs()
        self.pending_mode_request: ModeRequest | None = None
        self._stopped_since: int | None = None
        self._last_time = -1
        self._last_event_time = -1
        self._clear_sequence()
        # Tickets innerhalb derselben Instanz nicht wiederverwenden (alte Quittungen).

    def _clear_sequence(self):
        self.double_count = 0
        self._first_double: int | None = None
        self._last_double: int | None = None

    def _request_mode(self, now, target, *, activate=False, restore=False):
        self._serial += 1
        self.pending_mode_request = ModeRequest(self._serial, target, now, activate, restore)

    @property
    def speed_override_kmh(self) -> int | None:
        # None delegiert an den unveränderten Original-/Regionswert (Zielgerät: 20).
        # 30 ist nur eine Modellanforderung; Originalschutz hat immer Vorrang.
        return 30 if self.state is not State.NORMAL else None

    def sample(
        self, now: int, event: int | None, inputs: Inputs, *,
        mode_ack: int | None = None, dashboard_event: bool = False,
    ) -> list[Action]:
        if type(now) is not int or now < 0 or now < self._last_time:
            raise ValueError("Monotone, nichtnegative ganze Millisekunden erforderlich.")
        if event is not None and (type(event) is not int or not 0 <= event <= 255):
            raise ValueError("OEM-Ereignis muss ein Byte oder None sein.")
        if mode_ack is not None and (type(mode_ack) is not int or mode_ack <= 0):
            raise ValueError("Bestätigung verlangt ein positives Modusticket.")
        if not isinstance(inputs, Inputs):
            raise ValueError("Atomarer Inputs-Snapshot erforderlich.")
        if type(dashboard_event) is not bool:
            raise ValueError("Dashboard-Unterbrechung muss boolesch sein.")
        event = event or None
        duplicate = event is not None and now == self._last_event_time
        self._last_time = now
        if event is not None:
            self._last_event_time = now
        previous = self.inputs
        self.inputs = inputs
        was_ssm = self.state is not State.NORMAL
        out = []
        if inputs.powered is True and inputs.stopped:
            if self._stopped_since is None:
                self._stopped_since = now
        else:
            self._stopped_since = None
        stopped = (
            self._stopped_since is not None
            and now - self._stopped_since >= self.timing.standstill_ms
        )
        eligible = self.enabled and inputs.activation_safe and stopped
        if not eligible or dashboard_event or duplicate or event not in (None, 2):
            self._clear_sequence()
        if self._first_double is not None and (
            now - self._first_double > self.timing.sequence_ms
            or now - self._last_double > self.timing.double_gap_ms
        ):
            self._clear_sequence()

        pending = self.pending_mode_request
        if pending and now - pending.issued_at > self.timing.confirm_ms:
            self.pending_mode_request = None
            self._clear_sequence()
            pending = None
        if mode_ack is not None:
            self.pending_mode_request = None
            if (
                pending is None or pending.ticket != mode_ack
                or inputs.mode is not pending.target or inputs.telemetry_valid is not True
            ):
                self._clear_sequence()
            elif (
                pending.activate_after and self.double_count == 3
                and eligible and inputs.mode is Mode.SPORT and event is None
                and not dashboard_event and self.state is State.NORMAL
            ):
                self.state = State.ACTIVE
                self._clear_sequence()
                out.append(Action.ACTIVATE)
            elif pending.activate_after:
                self._clear_sequence()
        elif previous.mode is not inputs.mode and pending is None:
            self._clear_sequence()

        if inputs.powered is not True:
            self.state = State.NORMAL
            self.pending_mode_request = None
            self._clear_sequence()
        elif self.state is not State.NORMAL:
            unsafe = (
                inputs.fault is not False or inputs.locked is not False
                or inputs.telemetry_valid is not True or inputs.mode is not Mode.SPORT
                or type(inputs.speed_mm_s) is not int or dashboard_event
                or inputs.oem_reserved is not False
            )
            if unsafe and self.state is State.ACTIVE:
                self.state = State.EXIT_PENDING
                out.append(Action.DEFER_EXIT)
            if self.state is State.EXIT_PENDING and stopped:
                if inputs.mode is Mode.SPORT:
                    self.state = State.NORMAL
                    self.pending_mode_request = None
                    self._clear_sequence()
                    out.append(Action.DEACTIVATE)
                elif inputs.activation_safe and self.pending_mode_request is None:
                    self._request_mode(now, Mode.SPORT, restore=True)
                    out.append(Action.RESTORE_SPORT)

        if duplicate:
            return out + [Action.REJECT]
        if event is None:
            return out
        if event == 1:
            return out + [Action.LIGHT]
        if event == 3:
            return out + [Action.LONG_PRESS]
        # Reservierte/noch unbekannte OEM-Kontexte werden nie durch SSM abgefangen.
        if event != 2 or inputs.oem_reserved is not False or inputs.powered is not True:
            return out + [Action.OEM_EVENT]
        if was_ssm:
            if self.state is State.ACTIVE:
                self.state = State.EXIT_PENDING
                out.append(Action.DEFER_EXIT if not stopped else Action.DEACTIVATE)
                if stopped:
                    self.state = State.NORMAL
                self._clear_sequence()
            # Während vorgemerkter Rückkehr wird kein normaler Moduswechsel ausgelöst.
            return out

        # Jedes normale Doppelereignis bleibt eine OEM-Aktion, auch ohne SSM-Freigabe.
        if self.pending_mode_request is not None:
            self._clear_sequence()  # Vorherige Originalaktion noch nicht quittiert.
        if eligible and self._last_double is not None:
            gap = now - self._last_double
            if not self.timing.double_min_ms <= gap <= self.timing.double_gap_ms:
                self._clear_sequence()
        if eligible:
            if self.double_count == 0:
                self._first_double = now
            self.double_count += 1
            self._last_double = now
        if isinstance(inputs.mode, Mode):
            self._request_mode(
                now, next_stock_mode(inputs.mode), activate=self.double_count == 3,
            )
        return out + [Action.NEXT_MODE]

    def display(self, frame: Mapping) -> dict:
        result = dict(frame)
        result["mode_icons"] = (
            frozenset(Mode) if self.state is not State.NORMAL
            else frozenset((self.inputs.mode,)) if self.inputs.mode is not None
            else frozenset()
        )
        return result


def next_stock_mode(mode: Mode) -> Mode:
    order = (Mode.WALK, Mode.DRIVE, Mode.SPORT)
    return order[(order.index(mode) + 1) % len(order)]
