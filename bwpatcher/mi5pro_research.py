#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BW Patcher
# Copyright (C) 2024-2026 ScooterTeam
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/

"""Schreibgeschützte Bee2-Analyse; kein Patcher und kein Firmwareexport.

Die SDK-Strukturen und unabhängig geprüften Bereiche sind im Forschungsbericht
verlinkt. Adressen im entpackten APP sind keine Offsets der OTA-Datei.
"""

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import lzma
from pathlib import Path
import struct


APP_SHA256 = "95edba0d2d4a46405bfbb1a433b7ad4c1c72fc1787bc76eefe99a727c711bbae"
APP_BASE = 0x0080E000
MAX_IMAGE_SIZE = 1024 * 1024
MAX_BLOCK_SIZE = 0x4000
BLOCK_MORE = 0xFFFDFF00
BLOCK_LAST = 0xFFFFFF00


class AnalysisError(ValueError):
    """Unvollständige, fremde oder intern widersprüchliche Analysedaten."""


@dataclass(frozen=True)
class DecodedBLE:
    app: bytes = field(repr=False)
    report: dict


def checked_slice(data: bytes, offset: int, size: int) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise AnalysisError("Bereich ausserhalb der vollständigen Eingabe.")
    return data[offset:offset + size]


def control_header(data: bytes, offset: int = 0) -> dict:
    ic, secure, flags, image_id, crc, length = struct.unpack(
        "<BBHHHI", checked_slice(data, offset, 12)
    )
    if ic != 5 or length <= 0 or length > MAX_IMAGE_SIZE:
        raise AnalysisError("Kein unterstützter Bee2-Header oder unzulässige Länge.")
    return {
        "ic_type": ic, "secure_version": secure, "flags": flags,
        "image_id": image_id, "crc16": crc, "payload_length": length,
        "image_type": (flags >> 13) & 7,
        "xip": bool(flags & 1), "encrypted_flag": bool(flags & 2),
        "load_when_boot": bool(flags & 4),
        "encrypted_load_flag": bool(flags & 8),
        "key_selector": (flags >> 4) & 7,
    }


def normal_image_digest(data: bytes, offset: int = 0) -> dict:
    """Beobachtete Bee2-SHA-Bereiche; keine Signatur-/Vertrauensprüfung."""
    header = control_header(data, offset)
    size = 0x400 + header["payload_length"]
    image = checked_slice(data, offset, size)
    stored = image[0x174:0x194].hex()
    covered = image[12:0x174] + image[0x194:0x2f0] + image[0x3f0:]
    computed = hashlib.sha256(covered).hexdigest()
    return {"size": size, "stored": stored, "computed": computed,
            "valid": stored == computed}


def decode_compressed_app(data: bytes, offset: int) -> DecodedBLE:
    """96-Byte-Header und begrenzte LZMA-alone-Blöcke intern entpacken.

    Hashprüfung erfolgt vor Dekompression. Jeder Block ist nach Eingabe,
    Ausgabemenge und Decoder-Speicher begrenzt. Die Originalbytes bleiben gleich.
    """
    header = control_header(data, offset)
    if header["image_id"] != 0x2793 or header["image_type"] != 1:
        raise AnalysisError("Kein unterstütztes komprimiertes APP-Image.")
    raw_header = checked_slice(data, offset, 96)
    algorithm = struct.unpack_from("<I", raw_header, 32)[0]
    if algorithm != 1:
        raise AnalysisError("Nicht unterstützter Kompressionsalgorithmus.")
    payload = checked_slice(data, offset + 96, header["payload_length"])
    stored = raw_header[36:68].hex()
    actual = hashlib.sha256(payload).hexdigest()
    if stored != actual:
        raise AnalysisError("SHA-256 des komprimierten APP stimmt nicht.")

    cursor = 0
    pieces = []
    blocks = []
    output_size = 0
    while True:
        marker, unpacked_size, packed_size = struct.unpack(
            "<IHH", checked_slice(payload, cursor, 8)
        )
        if marker not in (BLOCK_MORE, BLOCK_LAST):
            raise AnalysisError("Unbekannte LZMA-Blockmarkierung.")
        if not 0 < unpacked_size <= MAX_BLOCK_SIZE or packed_size < 13:
            raise AnalysisError("Unzulässige Blocklänge.")
        output_size += unpacked_size
        if output_size > MAX_IMAGE_SIZE:
            raise AnalysisError("Entpacktes Image überschreitet die Analysegrenze.")
        packed = checked_slice(payload, cursor + 8, packed_size)
        try:
            decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=8 * 1024 * 1024)
            plain = decoder.decompress(packed, max_length=unpacked_size + 1)
        except lzma.LZMAError as exc:
            raise AnalysisError("Ungültiger oder zu speicherintensiver LZMA-Block.") from exc
        if len(plain) != unpacked_size or not decoder.eof or decoder.unused_data:
            raise AnalysisError("LZMA-Blocklänge oder Streamende stimmt nicht.")
        blocks.append({
            "container_offset": offset + 96 + cursor,
            "decoded_offset": output_size - unpacked_size,
            "packed_size": packed_size, "unpacked_size": unpacked_size,
            "last": marker == BLOCK_LAST,
        })
        pieces.append(plain)
        cursor += 8 + packed_size
        if marker == BLOCK_LAST:
            break
    padding = payload[cursor:]
    if padding != b"\xff" * ((-cursor) % 4):
        raise AnalysisError("Ungültiges abschliessendes Vierbyte-Padding.")
    app = b"".join(pieces)
    inner = normal_image_digest(app)
    if inner["size"] != len(app) or not inner["valid"]:
        raise AnalysisError("Grösse oder SHA-256 des entpackten APP stimmt nicht.")
    if control_header(app)["image_type"] != 0:
        raise AnalysisError("Entpacktes APP hat keinen normalen Image-Typ.")
    return DecodedBLE(app, {
        "compressed_header": header,
        "compressed_offset": offset,
        "compressed_header_size": 96,
        "compressed_payload_sha256": actual,
        "compressed_payload_sha256_valid": True,
        "compression_algorithm": algorithm,
        "blocks": blocks, "padding_size": len(padding),
        "decoded_size": len(app), "decoded_sha256": hashlib.sha256(app).hexdigest(),
        "decoded_image_base": struct.unpack_from("<I", app, 0x28)[0],
        "decoded_image_digest": inner,
    })


def inspect_ble(data: bytes) -> DecodedBLE:
    """Das beobachtete Paketlayout prüfen, ohne Kandidatensuche im Nutzcode."""
    patch = control_header(data)
    if patch["image_id"] != 0x2792:
        raise AnalysisError("Das Paket beginnt nicht mit einem ROM-Patch-Image.")
    digest = normal_image_digest(data)
    if not digest["valid"]:
        raise AnalysisError("SHA-256 des ROM-Patch-Images stimmt nicht.")
    app_offset = (digest["size"] + 15) & ~15
    padding_size = app_offset - digest["size"]
    if checked_slice(data, digest["size"], padding_size) != b"\xff" * padding_size:
        raise AnalysisError("Ungültiges Padding zwischen PATCH und APP.")
    decoded = decode_compressed_app(data, app_offset)
    if app_offset + 96 + decoded.report["compressed_header"]["payload_length"] != len(data):
        raise AnalysisError("Unerwartete Zusatzdaten hinter dem APP-Container.")
    if data[12:28] != data[app_offset + 12:app_offset + 28] or data[12:28] != decoded.app[12:28]:
        raise AnalysisError("UUIDs der drei Image-Header stimmen nicht überein.")
    return DecodedBLE(decoded.app, {
        "patch_header": patch, "patch_digest": digest, **decoded.report,
        "ssm_patch_available": False,
    })


def thumb_evidence(app: bytes, start: int, size: int) -> list[dict]:
    """Ein begrenztes Original-Codefenster samt PC-relativen Referenzen lesen."""
    if hashlib.sha256(app).hexdigest() != APP_SHA256:
        raise AnalysisError("Die Fundstellen verlangen das exakt untersuchte APP.")
    import capstone

    cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    cs.detail = True
    result = []
    for insn in cs.disasm(checked_slice(app, start, size), APP_BASE + start):
        row = {"app_offset": insn.address - APP_BASE, "address": insn.address,
               "instruction": f"{insn.mnemonic} {insn.op_str}"}
        operands = insn.operands
        if insn.mnemonic in ("adr", "adr.w") and len(operands) == 2:
            row["reference_address"] = ((insn.address + 4) & ~3) + operands[1].imm
        elif (
            insn.mnemonic in ("ldr", "ldr.w") and len(operands) == 2
            and operands[1].type == capstone.arm.ARM_OP_MEM
            and operands[1].mem.base == capstone.arm.ARM_REG_PC
        ):
            literal = ((insn.address + 4) & ~3) + operands[1].mem.disp - APP_BASE
            row["literal_offset"] = literal
            row["reference_address"] = struct.unpack("<I", checked_slice(app, literal, 4))[0]
        elif insn.mnemonic in ("bl", "b.w", "b") and operands[0].type == capstone.arm.ARM_OP_IMM:
            row["branch_target"] = operands[0].imm
        result.append(row)
    return result


def hook_candidates(app: bytes, blocks: list[dict]) -> list[dict]:
    """Instruktionsgrenzen und Formatbezug belegen, keine Hook-Freigabe."""
    candidates = []
    for name, offset, expected, contract in (
        ("Vor ursprünglichem Tasten-Phasenautomaten", 0x8264, "bl #0x8161ce",
         "R0 liefert Phasenereignis; R4=0 und Klassifikatorzustand müssen erhalten bleiben."),
        ("Klassifikator-Aufruf vor der ursprünglichen Aktionsentscheidung", 0x82FC,
         "bl #0x816260", "R0 liefert klassifiziertes Ereignis; OEM-Langdruck/Reset erhalten."),
        ("Kopie des Modusbitsatzes in Anzeige-Slot 12", 0x611C,
         "strb.w r0, [r4, #0x60]", "R4=0x2088b0; R0 ist Bitmap, R5 bleibt live."),
        ("Lesen von Slot 12 vor der Anzeigeaggregation", 0xC76C,
         "ldrb.w r0, [r4, #0x60]", "R0 wird in R5 verodert; R1 und R4..R11 sind live."),
    ):
        instruction = thumb_evidence(app, offset, 4)
        if len(instruction) != 1 or instruction[0]["instruction"] != expected:
            raise AnalysisError("Hook-Kandidat hat nicht die belegte 4-Byte-Instruktion.")
        block = next(
            b for b in blocks
            if b["decoded_offset"] <= offset
            and offset + 4 <= b["decoded_offset"] + b["unpacked_size"]
        )
        candidates.append({
            "name": name, **instruction[0],
            "continuation_address": APP_BASE + offset + 4,
            "local_contract": contract,
            "compressed_block_container_offset": block["container_offset"],
            "direct_ota_byte_offset_exists": False,
            "approved_for_injection": False,
            "missing": [
                "Reservierter ausführbarer Speicher und private RAM-Belegung",
                "Vollständiger Aufruf-/Interrupt-/Timingvertrag auf Hardware",
                "Originale Integritäts- und Updateanforderungen unverändert erfüllen",
                "Kohärente MCU/BLE-Zustandsübertragung und Fehlerpriorität",
            ],
        })
    return candidates


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ble", type=Path)
    parser.add_argument("--evidence", action="store_true", help="Belegte APP-Codefenster als JSON")
    args = parser.parse_args(argv)
    from bwpatcher.ssm_firmware import ORIGINALS

    try:
        data = args.ble.read_bytes()
        if hashlib.sha256(data).hexdigest() != ORIGINALS["ble"]["sha256"]:
            raise AnalysisError("Kein exakt identifiziertes BLE-Original 2.7.0_0015.")
        decoded = inspect_ble(data)
        report = decoded.report
        if args.evidence:
            report["hook_candidates"] = hook_candidates(decoded.app, report["blocks"])
            report["code_windows"] = {
                name: thumb_evidence(decoded.app, start, size)
                for name, start, size in (
                    ("key_phase", 0x81ce, 0x92),
                    ("key_multiclick", 0x8260, 0x74),
                    ("key_dispatch", 0x82d4, 0x40),
                    ("key_double_dispatch", 0x8530, 0x26),
                    ("key_five_dispatch", 0x85b6, 0x3a),
                    ("timer_registration", 0x19712, 0x6a),
                    ("io_registration", 0xc044, 0x34),
                    ("timer_event", 0x9e34, 0x1e),
                    ("io_key_handler", 0x9e18, 0x1c),
                    ("mode_cycle", 0x80aa, 0xb4),
                    ("display_copy", 0x60f4, 0x46),
                    ("display_send", 0xc6b2, 0x168),
                    ("controller_status_builder", 0x3940, 0x7c),
                    ("controller_frame_fields", 0x39f0, 0xcc),
                )
            }
    except (OSError, AnalysisError) as exc:
        parser.exit(1, f"Analyse abgebrochen: {exc}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
