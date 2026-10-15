#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Schreibgeschützte Identitäts-/Strukturprüfung der untersuchten Originale.

Ein passender Hash identifiziert nur die untersuchte Datei, keine SSM-fähige
Firmware. Es existiert absichtlich weder eine Patchfreigabe noch ein Export.
"""

import argparse
import binascii
import hashlib
import json
from pathlib import Path


ORIGINALS = {
    "mcu": {
        "version": "0007",
        "size": 149504,
        "md5": "aabaad0de541d7c79ca24d28c45ba097",
        "sha256": "ddcd65400c4fbdb45cb4cdbec2e812026d7bc6cb755fd9dd0180800caed5f9b8",
    },
    "ble": {
        "version": "2.7.0_0015",
        "size": 152552,
        "md5": "1c76ba994d8326dca0203a424dc09ff6",
        "sha256": "061d34cac06fb31d93ff8f47650cd09d61fa46e7a883b35c23f35cabff1e6df7",
    },
}


def crc16(data: bytes, offset: int, size: int) -> str:
    """CRC-16/XMODEM wie CorePatcher, mit vollständiger Bereichsprüfung."""
    if offset < 0 or size <= 0 or offset + size > len(data):
        raise ValueError("CRC-Bereich liegt ausserhalb der vollständigen Datei.")
    return binascii.crc_hqx(data[offset:offset + size], 0).to_bytes(2, "big").hex()


def inspect_mcu(data: bytes) -> dict:
    """Bekanntes BW/ES32-Layout prüfen, ohne die Eingabe zu verändern.

    Layoutbelege stehen in docs/supersport/BERICHT.md. Andere Layouts werden
    nicht geraten. Diese Strukturprüfung allein identifiziert kein Original.
    """
    if len(data) < 0x800:
        raise ValueError("BW-Paket ist kürzer als sein 0x800-Byte-Vorspann.")
    size = int.from_bytes(data[:4], "big")
    if 0x800 + size != len(data):
        raise ValueError("BW-Längenfeld und Dateigrösse stimmen nicht überein.")
    if data[0x22:0x2e] != b"000700010001" or data[0x12:0x16] != b"0108":
        # 0108 ist das separate Paketfeld, nicht die Katalogversion 0007.
        raise ValueError("Erwartete Mi5Pro-Kennung/Paketkennung fehlt.")
    marker = b"SZMC-ES-ZM-0283M"
    if data.count(marker) != 1:
        raise ValueError("ES32-Kennung fehlt oder ist nicht eindeutig.")
    es_header = data.index(marker) - 0x10
    if es_header < 0x800:
        raise ValueError("ES32-Kennung liegt ausserhalb des BW-Nutzbereichs.")
    es_code = es_header + 0x80
    es_size = int.from_bytes(data[es_header + 6:es_header + 8], "big")
    # Am exakten Original nachgewiesen: das CRC-Feld bei 0x0a deckt den
    # ES32-Teil bis EOF ab, nicht den gesamten angekündigten BW-Nutzbereich.
    # CorePatcher erreicht dasselbe durch ein überlanges Python-Slice.
    # Hier wird der tatsächlich beobachtete Bereich explizit begrenzt.
    outer_crc_size = len(data) - es_header
    outer_crc = crc16(data, es_header, outer_crc_size)
    inner_crc = crc16(data, es_code, es_size)
    stored_outer = data[0x0a:0x0c].hex()
    stored_inner = data[es_header + 0x30:es_header + 0x32].hex()
    return {
        "package_body_offset": 0x800,
        "package_body_size": size,
        "package_version_field": data[0x12:0x16].decode("ascii"),
        "es_header_offset": es_header,
        "es_code_offset": es_code,
        "es_code_size": es_size,
        "outer_crc_offset": es_header,
        "outer_crc_size": outer_crc_size,
        "outer_crc": {"stored": stored_outer, "computed": outer_crc},
        "inner_crc": {"stored": stored_inner, "computed": inner_crc},
        "checksums_valid": stored_outer == outer_crc and stored_inner == inner_crc,
    }


def assess_firmware(data: bytes, component: str) -> dict:
    if component not in ORIGINALS:
        raise ValueError("Komponente muss 'mcu' oder 'ble' sein.")
    expected = ORIGINALS[component]
    sha = hashlib.sha256(data).hexdigest()
    identified = sha == expected["sha256"] and len(data) == expected["size"]
    result = {
        "model": "xiaomi.scooter.5pro",
        "component": component,
        "expected_version": expected["version"],
        "size": len(data),
        "sha256": sha,
        "original_identified": identified,
        "ssm_patch_available": False,
        "issues": [],
    }
    if not identified:
        result["issues"].append("Datei stimmt nicht mit dem untersuchten Original überein.")
    if component == "mcu":
        try:
            result["structure"] = inspect_mcu(data)
            if not result["structure"]["checksums_valid"]:
                result["issues"].append("Mindestens eine MCU-Checksumme ist ungültig.")
        except ValueError as exc:
            result["issues"].append(str(exc))
    else:
        from bwpatcher.mi5pro_research import inspect_ble, AnalysisError

        try:
            result["structure"] = inspect_ble(data).report
        except AnalysisError as exc:
            result["issues"].append(str(exc))
        result["issues"].append(
            "SSM-Integration und elektrische Anzeige sind weiterhin ungeprüft; "
            "Hashprüfungen ersetzen keine Herstellersignaturprüfung."
        )
    return result


def disassemble_mcu(data: bytes) -> list[dict]:
    """Belegte Fundstellen als Dateioffsets, niemals als Patchanweisungen.

    Die Bereiche stammen aus dem exakt per SHA-256 identifizierten Original.
    Für andere Dateien darf diese Zuordnung nicht wiederverwendet werden.
    """
    if not assess_firmware(data, "mcu")["original_identified"]:
        raise ValueError("Disassemblierung dieser Fundstellen erfordert das exakte Original.")
    import capstone
    import struct

    cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    cs.detail = True
    result = []
    for start, end in (
        (0x1d0c6, 0x1d0f2), (0x1d132, 0x1d144),
        (0x203b2, 0x203e4), (0x204a0, 0x20502),
    ):
        for insn in cs.disasm(data[start:end], start):
            entry = {
                "file_offset": hex(insn.address),
                "instruction": f"{insn.mnemonic} {insn.op_str}",
            }
            if (
                insn.mnemonic == "ldr" and len(insn.operands) == 2
                and insn.operands[1].type == capstone.arm.ARM_OP_MEM
                and insn.operands[1].mem.base == capstone.arm.ARM_REG_PC
            ):
                literal = ((insn.address + 4) & ~3) + insn.operands[1].mem.disp
                entry["literal_file_offset"] = hex(literal)
                entry["literal_value"] = hex(struct.unpack_from("<I", data, literal)[0])
            result.append(entry)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcu", type=Path, help="Originale MCU-Datei 0007")
    parser.add_argument("--ble", type=Path, help="Originale BLE-Datei 2.7.0_0015")
    parser.add_argument("--disassemble", action="store_true", help="Belegte MCU-Fundstellen ausgeben")
    args = parser.parse_args(argv)
    if args.mcu is None and args.ble is None:
        parser.error("Mindestens --mcu oder --ble angeben.")
    if args.disassemble and args.mcu is None:
        parser.error("--disassemble benötigt --mcu.")
    reports = []
    for component in ORIGINALS:
        path = getattr(args, component)
        if path is not None:
            try:
                data = path.read_bytes()
                report = assess_firmware(data, component)
                if component == "mcu" and args.disassemble and report["original_identified"]:
                    report["disassembly"] = disassemble_mcu(data)
                reports.append(report)
            except OSError as exc:
                parser.exit(2, f"Datei nicht lesbar: {exc}\n")
    print(json.dumps(reports, indent=2, ensure_ascii=False))
    return 0 if all(r["original_identified"] for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
