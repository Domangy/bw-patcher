#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Ausführbare SSM-Spezifikation. Keine Firmwareintegration, kein Hardwarezugriff.

Alle Zeiten sind monotone Millisekunden; der Aufrufer muss regelmässig abtasten
und zusammengehörige Dashboard-/Sicherheitsereignisse atomar liefern. Die
Zeitkonstanten sind Entwurfswerte, keine rekonstruierten Xiaomi-Konstanten.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


SSM_STATUS = "Simulation vorhanden · Firmware-Patch nicht verfügbar · Hardware ungeprüft"
SSM_BLOCK_REASON = (
    "SSM ist ausschliesslich als Offline-Simulation implementiert. "
    "Verifizierte Tasten-, Sicherheits- und Display-Hooks fehlen; "
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


class Gesture(str, Enum):
    START = "start"
    SINGLE = "single"
    DOUBLE = "double"
    FIVE = "five"
    LONG = "long"
    REJECTED = "rejected"


class Action(str, Enum):
    LIGHT = "original_light_toggle"
    NEXT_MODE = "original_next_mode"
    LONG_PRESS = "original_long_press"
    ACTIVATE = "ssm_activate"
    DEACTIVATE = "ssm_deactivate"
    DEFER_EXIT = "ssm_exit_at_standstill"
    REJECT = "sequence_rejected"


@dataclass(frozen=True)
class Timing:
    debounce_ms: int = 30
    gap_ms: int = 350
    sequence_ms: int = 1800
    long_ms: int = 800
    standstill_ms: int = 500

    def __post_init__(self):
        for value in vars(self).values():
            if type(value) is not int or value <= 0:
                raise ValueError("Zeiten müssen positive ganze Millisekunden sein.")
        if not self.debounce_ms < self.gap_ms < self.sequence_ms:
            raise ValueError("Entprellung < Klickpause < Sequenzdauer erforderlich.")
        if not self.debounce_ms < self.long_ms < self.sequence_ms:
            raise ValueError("Entprellung < Langdruck < Sequenzdauer erforderlich.")


@dataclass(frozen=True)
class Inputs:
    # None bedeutet unbekannt, niemals eine implizite Freigabe.
    powered: bool = False
    mode: Mode = Mode.SPORT
    speed_mm_s: int | None = None
    fault: bool | None = None
    throttle_released: bool | None = None
    locked: bool | None = None
    telemetry_valid: bool = False

    @property
    def stopped(self) -> bool:
        return (
            self.telemetry_valid is True
            and type(self.speed_mm_s) is int
            and self.speed_mm_s == 0
        )

    @property
    def activation_allowed(self) -> bool:
        return (
            self.powered is True
            and self.mode is Mode.SPORT
            and self.stopped
            and self.fault is False
            and self.throttle_released is True
            and self.locked is False
        )


class ButtonRecognizer:
    """Entprellt Pegel und entscheidet erst nach Ablauf der Klickpause.

    Exakt fünf Klicks werden erst nach Ruhe bestätigt: Ein sechster Klick
    innerhalb des Fensters verwirft die ganze Sequenz. Ein begonnener neuer
    Druck verhindert die vorzeitige Auswertung während seiner Entprellung.
    """

    def __init__(self, timing: Timing = Timing()):
        self.timing = timing
        self.raw = self.stable = False
        self.raw_since = 0
        self.press_since: int | None = None
        self.first_press: int | None = None
        self.last_release: int | None = None
        self.count = 0
        self.blocked = False
        self.long_sent = False
        self.last_time = -1
        self.last_raw = False

    def cancel(self, now: int):
        self.first_press = None
        self.count = 0
        self.blocked = True
        self.last_release = now

    def _finish(self) -> Gesture | None:
        count = self.count
        self.first_press = None
        self.last_release = None
        self.count = 0
        if self.blocked:
            self.blocked = False
            return None
        return {1: Gesture.SINGLE, 2: Gesture.DOUBLE, 5: Gesture.FIVE}.get(
            count, Gesture.REJECTED if count else None
        )

    def update(self, now: int, pressed: bool, *, cancel: bool = False) -> list[Gesture]:
        if type(now) is not int or now < 0 or type(pressed) is not bool:
            raise ValueError("Ganzzahlige Zeit und boolescher Tastenpegel erforderlich.")
        if now < self.last_time:
            raise ValueError("Zeit darf nicht rückwärts laufen; bei Neustart reset() aufrufen.")
        out = []
        if now == self.last_time and pressed != self.last_raw:
            cancel = True  # Widersprüchliche Pegel am selben Zeitpunkt.
        self.last_time, self.last_raw = now, pressed
        if cancel:
            self.cancel(now)

        # Eine neue rohe Flanke an/ab der Frist beginnt eine neue Sequenz.
        if (
            not self.stable and not self.raw and self.last_release is not None
            and now - self.last_release >= self.timing.gap_ms
        ):
            result = self._finish()
            if result is not None:
                out.append(result)

        if pressed != self.raw:
            self.raw, self.raw_since = pressed, now
        if self.raw != self.stable and now - self.raw_since >= self.timing.debounce_ms:
            self.stable = self.raw
            if self.stable:
                self.press_since = now
                self.long_sent = False
                if self.first_press is None and not self.blocked:
                    self.first_press = now
                    out.append(Gesture.START)
            else:
                held = now - self.press_since if self.press_since is not None else 0
                if held >= self.timing.long_ms and not self.long_sent:
                    out.append(Gesture.LONG)
                    self.cancel(now)
                elif not self.long_sent and not self.blocked:
                    self.count += 1
                    if self.count > 5:
                        out.append(Gesture.REJECTED)
                        self.cancel(now)
                self.last_release = now
                self.press_since = None

        if (
            self.stable and self.press_since is not None and not self.long_sent
            and now - self.press_since >= self.timing.long_ms
        ):
            self.long_sent = True
            self.cancel(now)
            out.append(Gesture.LONG)

        if (
            self.first_press is not None
            and now - self.first_press >= self.timing.sequence_ms
        ):
            self.cancel(now)
            out.append(Gesture.REJECTED)
        return out


class SuperSportSimulation:
    """Logisches Modell mit originalen Aktionen als Ausgaben, ohne Motorbefehle.

    Der Aufrufer bleibt für Originalbedienung, Telemetriefrische, Fehlervorrang
    und die spätere Bestätigung tatsächlicher Firmwarezustände verantwortlich.
    """

    def __init__(self, *, enabled: bool = False, timing: Timing = Timing()):
        self.enabled = enabled
        self.timing = timing
        self.reset()

    def reset(self):
        """Volatilen Zustand verwerfen, auch bei Warmstart/watchdog reset."""
        self.state = State.NORMAL
        self.buttons = ButtonRecognizer(self.timing)
        self.inputs = Inputs()
        self._stopped_since: int | None = None
        self._armed = False
        self._sequence_from_ssm = False

    @property
    def speed_override_kmh(self) -> int | None:
        # None: Originalbegrenzung und sämtliche Originalschutzfunktionen.
        return 30 if self.state is not State.NORMAL else None

    def sample(
        self, now: int, pressed: bool, inputs: Inputs, *, dashboard_event: bool = False
    ) -> list[Action]:
        # Zuerst Zeit/Pegel validieren, ohne den Zustand zu verändern.
        if type(now) is not int or now < 0 or now < self.buttons.last_time:
            raise ValueError("Monotone, nichtnegative ganze Millisekunden erforderlich.")
        if type(pressed) is not bool:
            raise ValueError("Boolescher Tastenpegel erforderlich.")
        previous = self.inputs
        self.inputs = inputs
        if inputs.stopped and inputs.powered:
            if self._stopped_since is None:
                self._stopped_since = now
        else:
            self._stopped_since = None
        stopped = (
            self._stopped_since is not None
            and now - self._stopped_since >= self.timing.standstill_ms
        )
        eligible = self.enabled and inputs.activation_allowed and stopped
        if not eligible:
            self._armed = False

        out = []
        if not inputs.powered:
            self.state = State.NORMAL
            self._armed = False
        elif self.state is not State.NORMAL:
            unsafe = (
                inputs.fault is not False or inputs.locked is not False
                or not inputs.telemetry_valid or inputs.mode is not Mode.SPORT
                or type(inputs.speed_mm_s) is not int
                or dashboard_event
            )
            if unsafe and self.state is State.ACTIVE:
                self.state = State.EXIT_PENDING
                out.append(Action.DEFER_EXIT)
            if self.state is State.EXIT_PENDING and stopped:
                self.state = State.NORMAL
                out.append(Action.DEACTIVATE)

        changed = (
            previous.mode != inputs.mode or previous.powered != inputs.powered
            or previous.locked != inputs.locked or previous.fault != inputs.fault
            or previous.telemetry_valid != inputs.telemetry_valid
        )
        gestures = self.buttons.update(
            now, pressed, cancel=dashboard_event or changed or not inputs.powered
        )
        for gesture in gestures:
            if gesture is Gesture.START:
                self._sequence_from_ssm = self.state is not State.NORMAL
                self._armed = bool(eligible and not self._sequence_from_ssm)
            elif gesture is Gesture.LONG:
                self._armed = False
                out.append(Action.LONG_PRESS)
            elif not inputs.powered or inputs.locked is not False:
                continue
            elif gesture is Gesture.SINGLE:
                out.append(Action.LIGHT)
            elif gesture is Gesture.DOUBLE:
                if self.state is State.NORMAL:
                    # Eine schon während SSM begonnene Folge darf nach der
                    # automatischen Rückkehr keinen weiteren Moduswechsel auslösen.
                    if not self._sequence_from_ssm:
                        out.append(Action.NEXT_MODE)
                elif stopped:
                    self.state = State.NORMAL
                    out.append(Action.DEACTIVATE)
                elif self.state is State.ACTIVE:
                    self.state = State.EXIT_PENDING
                    out.append(Action.DEFER_EXIT)
            elif gesture is Gesture.FIVE:
                if self.state is State.NORMAL and self._armed and eligible:
                    self.state = State.ACTIVE
                    out.append(Action.ACTIVATE)
                else:
                    out.append(Action.REJECT)
            elif gesture is Gesture.REJECTED:
                out.append(Action.REJECT)
        return out

    def display(self, frame: Mapping) -> dict:
        """Nur logische Symbole ersetzen; keine Hardwarebits/Protokollbefehle.

        Alle sonstigen, auch unbekannten Felder werden unverändert übernommen.
        Dauerleuchten ist hier ein Zustand, kein Blinktimer.
        """
        result = dict(frame)
        result["mode_icons"] = (
            frozenset(Mode) if self.state is not State.NORMAL
            else frozenset((self.inputs.mode,))
        )
        return result


def next_stock_mode(mode: Mode) -> Mode:
    """Abstrakte Reihenfolge aus dem Auftrag, keine MCU-Modusnummern."""
    order = (Mode.WALK, Mode.DRIVE, Mode.SPORT)
    return order[(order.index(mode) + 1) % len(order)]
