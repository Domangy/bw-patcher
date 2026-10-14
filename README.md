# bw-patcher

Research tool for analyzing and modifying firmware parameters on Brightway-based controllers.

## ⚠️ IMPORTANT SAFETY WARNING

**Modifying device firmware can be dangerous and illegal.**

- May void your warranty
- May violate local laws and regulations
- Creates serious safety risks
- Modified devices may be illegal to operate
- You assume ALL liability for injuries, accidents, and legal consequences

**Use at your own risk. This software is for educational and research purposes only.**

👉 Read the full [PRINCIPLES.md](PRINCIPLES.md) and [LEGAL_DISCLAIMER.md](LEGAL_DISCLAIMER.md) before using this software.

## Setup

This patcher requires Python and the `keystone-engine` package installed.

### Using Poetry (recommended)
```bash
poetry install
```

### Using pip
```bash
pip install -r requirements.txt
```

## Supported Models

- Mi4
- Mi4Pro2nd
- Mi4Lite
- Mi5
- Mi5Pro
- Mi5Max
- Mi5Elite
- Ultra4

## Available Modifications

This tool can modify various firmware parameters. The specific parameters available depend on the device model and firmware version.

**WARNING:** Modifying firmware parameters may alter device behavior, void warranties, and create legal liability. Users assume all responsibility.

## Usage

### CLI
```bash
poetry run python -m bwpatcher --help

# Explicit model
poetry run python -m bwpatcher mi4 firmware.bin out.bin sls=25,chk

# Auto-detect model from header ([0x00, 0x80))
poetry run python -m bwpatcher auto firmware.bin out.bin sls=25,chk

# Header-only model detection
poetry run python -m bwpatcher detect firmware.bin
```

### GUI
```bash
poetry run streamlit run app.py
```

The GUI auto-selects the model from the uploaded firmware header when possible
(override via the model dropdown). A legal disclaimer must be accepted before use.

### Example Usage

Apply modifications to firmware:
```bash
poetry run python -m bwpatcher mi4 firmware.bin firmware_modified.bin patch1,patch2
```

**Note:** Always maintain backups of original firmware before modification.

## Mi5Pro: SuperSport Mode (SSM) — Forschungsstand

**Entwicklungsstufe 3: Simulation erfolgreich. Kein SSM-Firmware-Patch.**
Die Originaldateien MCU `0007` und BLE `2.7.0_0015` wurden lokal untersucht.
Das BLE-APP ist entpackt; originale Tasten-, Anzeige- und Modustransportroutinen
wurden offline ausgeführt. Drei unabhängige Anzeige-Bits sind bis zur Byte-Ausgabe
belegt. Ihre elektrische Wirkung und ein integrierter SSM-Patch bleiben ungeprüft.
Die SSM-Option bleibt gesperrt, auch mit `--experimental`.
Neue Aktivierung: drei getrennte OEM-Doppelklicks, mit normalen Moduswechseln
und bestätigtem Sportmodus nach dem dritten Wechsel. Einzelklick/Licht bleiben
OEM-Aktionen; ein Doppelklick beendet SSM im Stillstand. Bestehende Speed-Patches
erzeugen keinen zusätzlichen Fahrmodus.

Ausführlicher deutscher Bericht mit Hashes, Fundstellen, Einschränkungen und
nächsten Schritten: [SSM-Entwicklungsbericht](docs/supersport/BERICHT.md) und
[Fortsetzung mit Originalcode-Nachweisen](docs/supersport/FORTSETZUNG.md) sowie
[aktuelle Doppelklick-Spezifikation](docs/supersport/DOPPELKLICK.md).

```bash
# Reine Offline-Demo, ohne Firmware oder angeschlossenen Scooter
python -m bwpatcher.ssm_demo

# Originaldateien nur lesen; es wird keine Firmware ausgegeben
python -m bwpatcher.ssm_firmware --mcu /lokal/mcu_0007.bin --ble /lokal/ble_2.7.0_0015.bin

# Optionale Forschungsabhängigkeit für Originalcode-Ausführung
poetry install --with research
python -m bwpatcher.mi5pro_research /lokal/ble_2.7.0_0015.bin --evidence
python -m bwpatcher.mi5pro_emulator --ble /lokal/ble_2.7.0_0015.bin --mcu /lokal/mcu_0007.bin

# Neue Analysefälle, mit lokalen Originalen zusätzlich Originalcodeprüfungen
MI5PRO_FIRMWARE_DIR=/lokal/originale python -m pytest tests/test_mi5pro_research.py -q

# Tests ohne proprietäre Dateien (Originaltests werden übersprungen)
# Test- und GUI-Abhängigkeiten sind in poetry install enthalten.
python -m pytest tests -q
```

Die Streamlit-Oberfläche zeigt diesen Entwicklungsstand für Mi5Pro an.
Die GUI stellt weiterhin die abstrakte Simulation dar. Die neuen Werkzeuge
prüfen getrennt ausgewählte Originalfunktionen mit emulierter Peripherie.

## License

Licensed under CC BY-NC-SA 4.0 (NonCommercial, ShareAlike). See [LICENSE](LICENSE) for full terms.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing to this project.

## Disclaimer

This tool is provided for educational and research purposes only. The authors accept no liability for any consequences of using this software. See [LEGAL_DISCLAIMER.md](LEGAL_DISCLAIMER.md) for complete terms.
