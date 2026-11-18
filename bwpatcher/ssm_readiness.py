"""Read-only release check for Mi5Pro SuperSport research.

Never produces or transmits firmware. This is an intentionally conservative
release gate until integrated controller behaviour is hardware-validated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from bwpatcher.ssm_firmware import ORIGINALS, assess_firmware

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NAMES = {"mcu": "mcu_0007.bin", "ble": "ble_2.7.0_0015.bin"}
# These are unresolved, verified development blockers, not optional warnings.
BLOCKERS = (
    "Keine freigegebene Integration des SSM in BLE- und MCU-Firmware.",
    "Unabhaengige Absichtsfreigabe und echte Modus-/Reglerquittung fehlen.",
    "Speicher, Hook-Kontext, Stack, Interrupts und Peripherie nicht vollstaendig validiert.",
    "Brems-, Motor-, Temperatur-, Batterie- und Displaywirkung nicht am Geraet getestet.",
    "SSM-Firmwareexport ist im bestehenden Patcher ausdruecklich gesperrt.",
)


def check_image(path: Path, component: str) -> dict:
    expected = ORIGINALS[component]
    result = {
        "component": component,
        "path": str(path),
        "expected_version": expected["version"],
        "exists": path.is_file(),
        "original_verified": False,
    }
    if not result["exists"]:
        result["reason"] = "Originaldatei fehlt."
        return result
    data = path.read_bytes()
    size = len(data)
    sha256 = hashlib.sha256(data).hexdigest()
    result.update(size=size, sha256=sha256)
    if size != expected["size"] or sha256 != expected["sha256"]:
        result["reason"] = "Datei entspricht nicht der untersuchten Original-Firmware."
        return result
    # Stronger format and checksum validation from the original research code.
    assessment = assess_firmware(data, component)
    if not assessment["original_identified"] or "structure" not in assessment:
        result["reason"] = "Originaldatei oder Firmwarestruktur nicht bestaetigt."
        return result
    if component == "mcu" and not assessment["structure"].get("checksums_valid", False):
        result["reason"] = "Originale MCU-Checksummen sind nicht konsistent."
        return result
    result["original_verified"] = True
    result["reason"] = "Originaldatei und Firmwarestruktur exakt erkannt."
    if assessment["issues"]:
        result["notes"] = assessment["issues"]
    return result


def build_report(directory: Path) -> dict:
    checked = {part: check_image(directory / filename, part)
               for part, filename in NAMES.items()}
    return {
        "model": "xiaomi.scooter.5pro",
        "scope": "Ausschliesslich Offline-Softwarepruefung; keine Geraeteverbindung.",
        "images": checked,
        "originals_verified": all(x["original_verified"] for x in checked.values()),
        "simulation_implemented": True,
        "ssm_integrated_in_real_firmware": False,
        "hardware_validated": False,
        "flashable_ssm_image_available": False,
        "release_ready": False,
        "blocking_reasons": list(BLOCKERS),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originale", type=Path, default=PROJECT_ROOT / "originale")
    parser.add_argument("--output", type=Path, help="Optionaler JSON-Pruefbericht, KEINE Firmware")
    args = parser.parse_args(argv)
    report = build_report(args.originale)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    # A report command may succeed despite 'not release ready'; the JSON makes
    # the status explicit and cannot be confused with a flashable binary.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
