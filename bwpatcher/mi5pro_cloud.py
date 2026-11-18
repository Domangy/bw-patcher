"""Exakt belegten Mi5Pro-BLE-Originalcontainer aus Xiaomi-OTA-Download gewinnen.

Die Cloud-Antwort ist ein 153890-Byte-OTA-Download mit 1338 Byte Anhang.
Der Anhang wird weder entschluesselt noch als gueltige Signatur behauptet.
Nur eine exakt bekannte Bytefolge darf extrahiert werden. Kein Flashen.
"""
import argparse
import hashlib
from pathlib import Path

from bwpatcher.mi5pro_research import APP_SHA256, inspect_ble
from bwpatcher.ssm_firmware import ORIGINALS

CLOUD_SIZE = 153890
CLOUD_MD5 = "0d41b4df91f8d37b5f1355484e2b93c3"
CLOUD_SHA256 = "f8c801d50d36e258fda04f31d28276e2b576b227d32c7f356d9f98dac062e64e"


class CloudBLEMismatch(ValueError):
    pass


def extract_original_ble(download: bytes) -> bytes:
    """Gibt nur das bitidentische, strukturell verifizierte BLE-Original zurueck."""
    if type(download) is not bytes:
        raise TypeError("OTA-Download muss bytes sein.")
    if (len(download) != CLOUD_SIZE
            or hashlib.md5(download).hexdigest() != CLOUD_MD5
            or hashlib.sha256(download).hexdigest() != CLOUD_SHA256):
        raise CloudBLEMismatch("Unbekanntes Xiaomi-OTA-Paket: keine Extraktion.")
    length = ORIGINALS["ble"]["size"]
    original = download[:length]
    if hashlib.sha256(original).hexdigest() != ORIGINALS["ble"]["sha256"]:
        raise CloudBLEMismatch("BLE-Original stimmt nicht mit der Codex-Referenz ueberein.")
    if hashlib.md5(original).hexdigest() != ORIGINALS["ble"]["md5"]:
        raise CloudBLEMismatch("BLE-Original-MD5 stimmt nicht.")
    decoded = inspect_ble(original)
    if hashlib.sha256(decoded.app).hexdigest() != APP_SHA256:
        raise CloudBLEMismatch("Das dekomprimierte APP ist nicht das untersuchte Original.")
    return original


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Original-Xiaomi-OTA-Download")
    parser.add_argument("--output", required=True, type=Path, help="Ziel fuer exakten Originalteil")
    args = parser.parse_args(argv)
    original = extract_original_ble(args.input.read_bytes())
    if args.output.exists() and args.output.read_bytes() != original:
        parser.error("Ziel existiert und ist anders; keine Datei ueberschrieben.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(original)
    print(f"Original BLE exakt verifiziert ({len(original)} Bytes): {args.output}")
    print(f"SHA-256: {ORIGINALS['ble']['sha256']}")
    print(f"OTA-Anhang: {CLOUD_SIZE - len(original)} Bytes (nicht interpretiert)")
    print("Kein Firmware-Patch und kein Flash-Vorgang.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
