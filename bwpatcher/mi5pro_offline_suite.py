"""Reproducible offline-only Mi5Pro validation; never writes scooter or firmware."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

from bwpatcher.ssm_readiness import build_report

ROOT = Path(__file__).resolve().parent.parent
FILES = ("mcu_0007.bin", "ble_2.7.0_0015.bin")


def file_hashes(folder: Path) -> dict[str, str | None]:
    result = {}
    for name in FILES:
        path = folder / name
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return result


def run_suite(root: Path = ROOT, *, skip_tests: bool = False) -> tuple[dict, int]:
    original_dir = root / "originale"
    before = file_hashes(original_dir)
    preflight = build_report(original_dir)
    report = {
        "tool": "Mi5Pro offline-only evidence suite",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "originals_verified": preflight["originals_verified"],
        "firmware_hashes_before": before,
        "checks": {},
        "release_ready": False,
        "hardware_validated": False,
        "flashable_ssm_firmware_created": False,
    }
    rc = 0 if preflight["originals_verified"] else 2
    if not preflight["originals_verified"]:
        report["checks"]["originals"] = "FAILED: Both exact original images required."
    elif skip_tests:
        report["checks"]["pytest"] = "Not run (requested skip)"
    else:
        env = os.environ.copy()
        env["MI5PRO_FIRMWARE_DIR"] = str(original_dir)
        cloud = Path.home() / "scooter-cloud-tools" / "quarantine" / "ble_from_xiaomi_cloud_de_0015.bin"
        if cloud.is_file():
            env["MI5PRO_CLOUD_DOWNLOAD"] = str(cloud)
        args = [sys.executable, "-m", "pytest"]
        if os.name == "nt":
            # Unicorn 2.1.4 Windows VEH conflicts with pytest faulthandler.
            # The actual test cases remain enabled; process exit status is checked.
            args.extend(["-p", "no:faulthandler"])
        args.extend(["tests", "-q", "--tb=short"])
        run = subprocess.run(args, cwd=root, env=env, capture_output=True, text=True, errors="replace")
        report["checks"]["pytest"] = {
            "exit_code": run.returncode,
            "summary": [line.strip() for line in run.stdout.splitlines() if
                        " passed" in line or " failed" in line or " skipped" in line][-3:],
            "windows_faulthandler_conflict_avoided": os.name == "nt",
            "stdout": run.stdout[-2500:],
            "stderr": run.stderr[-1000:],
        }
        rc = run.returncode if run.returncode else 0
    after = file_hashes(original_dir)
    report["firmware_hashes_after"] = after
    report["originals_unchanged"] = before == after
    if not report["originals_unchanged"]:
        rc = 3
    report["success"] = rc == 0 and report["originals_unchanged"]
    return report, rc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true", help="Nur Originaldateien pruefen")
    args = parser.parse_args(argv)
    report, status = run_suite(skip_tests=args.skip_tests)
    dest = ROOT / "originale" / "OFFLINE_PRUEFBERICHT.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Originale verifiziert:", report["originals_verified"])
    print("Originaldateien unveraendert:", report["originals_unchanged"])
    tests = report["checks"].get("pytest")
    if isinstance(tests, dict):
        print("Pytest:", "; ".join(tests["summary"]) or "Keine Testzusammenfassung")
        print("Pytest Exit-Code:", tests["exit_code"])
        if tests["stderr"]:
            print("Pytest stderr (gekuerzt):", tests["stderr"][-300:])
    else:
        print("Pytest:", tests or "Nicht gestartet")
    print("Bericht:", dest)
    print("SSM flashbar:", False)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
