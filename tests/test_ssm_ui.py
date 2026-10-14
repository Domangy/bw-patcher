#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Streamlit-Integration mit synthetischem Header, ohne Firmwareexport."""

from io import BytesIO
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from bwpatcher.ssm_demo import demonstration


@pytest.mark.parametrize("experimental", [False, True])
def test_mi5pro_ui_keeps_ssm_disabled(monkeypatch, experimental):
    data = bytearray(0x100)
    data[0x12:0x16] = b"0108"
    data[0x22:0x2e] = b"000700010001"
    upload = BytesIO(data)
    upload.name = "synthetic.bin"
    monkeypatch.setattr(st, "file_uploader", lambda *a, **kw: upload)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    app.session_state["disclaimer_accepted"] = True
    if experimental:
        app.query_params["experimental"] = "1"
    app.run(timeout=20)
    assert not app.exception
    ssm = next(c for c in app.checkbox if c.label == "Enable SuperSport Mode (SSM)")
    assert ssm.disabled and not ssm.value
    assert any('3 getrennte Doppelklicks' in item.value for item in app.markdown)
    assert not any(b.label == "Apply patches" for b in app.button)
    # Bestehende Mi5Pro-Optionen bleiben zugänglich.
    assert any(c.label == "Sport (SLS)" and not c.disabled for c in app.checkbox)


def test_demonstration_exercises_activation_deferred_exit_and_restart():
    trace = demonstration()
    actions = [row['actions'] for row in trace[:-1] if row.get('actions')]
    activation = [["original_next_mode"]] * 3 + [["ssm_activate"]]
    assert actions == activation + [["ssm_exit_at_standstill"], ["ssm_deactivate"]] + activation
    confirmed = [row['confirmed_mode'] for row in trace if row.get('ack_source')]
    assert confirmed == ['walk', 'drive', 'sport'] * 2
    active = next(row for row in trace if row.get('actions') == ['ssm_activate'])
    assert active['mode_icons'] == ["drive", "sport", "walk"]
    assert active['confirmed_mode'] == 'sport'
    assert trace[-1]["state"] == "normal"
    assert trace[-1]["speed_override_kmh"] is None
