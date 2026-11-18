# Xiaomi Scooter 5 Pro – kompletter Offline-Binärkandidat (18.11.2026)

Dieser Bericht dokumentiert einen **nicht freigegebenen** Entwicklungsstand.
Es gibt keinen Installer, keine Flashdatei und keine Änderung am Scooter.

## Verifizierte MCU-Paketstruktur

Beim exakt identifizierten Original-MCU-Image `0007` mit 149'504 Bytes
wird der ES32-Code bei Dateioffset `0x19880` geladen. Das ursprüngliche
Längenfeld lautet `0xAE90`; nach dem Ende bei `0x24710` stehen innerhalb
derselben ursprünglichen Binärdatei **240 Bytes FF-Padding** bis `0x24800`.

Das neue Modul `bwpatcher/mi5pro_mcu_candidate_in_memory.py` platziert
den bereits in Unicorn erprobten 20-Byte-ARM-Thumb-Sonderzweig für
Modus 4 in einem **Bytestring im Arbeitsspeicher** bei Laufzeitadresse
`0xAE90`, erweitert die deklarierte ES32-Codelänge auf `0xAEB0` und
berechnet den inneren sowie den äusseren CRC-16/XMODEM neu.
Die Gesamtdateigrösse bleibt **149'504 Bytes**.

Vier gezielte Tests mit den echten Originaldateien sind bestanden.
Der MCU-Emulator führt den Zusatzcode jetzt aus den Imagebytes selbst aus,
nicht mehr aus einer künstlich hinzugefügten Emulatorseite bei `0xF000`.

Bei einem synthetischen Test-Seriennummerpräfix zeigt die Originalregion
für Sport den Rohwert 417 (ungefähr 20 km/h); der experimentelle
Modus 4 setzt den Rohwert 627 (ungefähr 30 km/h). Originalmodi 2, 3 und 11
lieferten in den verglichenen Emulationspfaden unveränderte Werte.

**Kritische Einschränkung:** Die zusätzlichen Bytes sind zwar im
ursprünglichen Dateipadding untergebracht, aber die tatsächliche
Bootloaderakzeptanz der verlängerten ES32-Codelänge ist nicht nachgewiesen.
Das native Mode-4-Hook umgeht die ursprüngliche Sport-Grenzklammer.
Das kann den Motorregler und die Sicherheit erheblich beeinflussen.
Ein CRC-Nachweis beweist keine Hersteller-Signaturakzeptanz.

## BLE-Firmware und gemeinsames Paket

Der experimentelle BLE-Hook enthält bisher:
- drei getrennte OEM-Doppelklicks im Emulatorszenario (Zeitfenster 600–1600 ms
  zwischen Doppelereignissen, Gesamtabstand höchstens 4000 ms);
- In einem weiteren experimentellen Schritt wird der 16-Bit-Zeitwert im
  BLE-RAM durch einen zusätzlichen nativen ARM-Thumb-Hook unmittelbar
  vor dem originalen Tastenklassifikator erhöht (APP+`0x82fc`).
  Die Zeit wird in diesem Pfad nicht mehr durch Python gesetzt.
  Die verwendeten Nullbyte-Codekandidaten bei APP+`0x2c42a`
  (16 Bytes) und APP+`0x2c448` (4-Byte-Adressliteral) sind
  **nicht als hardwareseitig frei nachgewiesen**. Die echte
  Aufrufperiode (nominal 10 ms) ist am Scooter ungeprüft;
- einen Aktiv-Zustand und Deaktivierung beim nächsten Doppelklick;
- eine native Thumb-Umleitung an der originalen UART-Sendefunktion,
  die bei aktiviertem Zustand den Modus von Sport `0x23` auf
  Sondermodus `0x24` setzt und die Frame-Prüfsumme aktualisiert.

`bwpatcher/mi5pro_dual_candidate_in_memory.py` kombiniert eine
vollständige **strukturell erneut dekodierbare BLE-Container-Bytefolge**
mit dem modifizierten MCU-ES32-Bytestring – nur im Arbeitsspeicher.

`tests/test_mi5pro_dual_candidate_in_memory.py` enthält zusätzliche
End-to-End-Prüfungen für die beiden neu verpackten Komponenten.
**Die drei gemeinsamen Tests wurden nach Wiederherstellung der Laptopverbindung
mit den echten Originaldateien erfolgreich ausgeführt.** Zusammen mit den
vier neuen MCU-Containerprüfungen bestanden alle sieben gezielten Tests.
Die vollständige Regressionstestsuite meldete **433 bestanden, 1 Warnung,
0 fehlgeschlagen** (18.11.2026, Windows, Unicorn/pytest). Auch nach
Integration des neuen ARM-Thumb-Zeitzählers wurden **433/433 Tests**
nochmals erfolgreich ausgeführt (28,05 Sekunden, 1 Capstone-Warnung).
Die elf gezielten Tests für die nativen Gesten und die gemeinsamen
Firmwarecontainer sind ebenfalls bestanden.

## Was eine echte Firmware-Freigabe weiterhin verhindert

1. **RAM- und Flash-Speicherbesitz:** Der BLE-Hook verwendet einen
   lediglich vermuteten Auffüllbereich und RAM bei `0x20B000`.
   Der MCU-Bootloader ist für die erweiterte ES32-Codelänge nicht
   gerätevalidiert. Auch ein gültiger Thumb-Branch garantiert keine
   sichere Ausführung auf der realen Hardware.
2. **Echte Eingaben:** In den Tests wird ein Tick-Zähler und ein
   zulässiger Sicherheitszustand durch Python gesetzt. Die
   echten Signale für Bremse, Gaspedal, Stillstand, Fehler,
   Verriegelung und Timeout sind nicht angeschlossen.
   Unterbrechungen durch andere OEM-Ereignisse sind nicht
   vollständig behandelt.
3. **Motor-Sicherheit:** Der Mode-4-Zweig setzt den höheren Zielwert
   ohne echten Nachweis für Bremsverhalten, Rekuperation, Strom-
   und Temperaturbegrenzung, BMS und Kommunikationsausfall.
   Die Schutzfunktionen bei 30 km/h sind nicht geprüft.
4. **Authentifizierung:** Innere CRC- und SHA-256-Werte reichen nicht
   zur Überprüfung einer OEM-Signatur oder einer erfolgreichen
   BLE-/MCU-Geräteinstallation. Auch die originale LZMA-Komprimierung
   ist nicht byteidentisch reproduziert.
5. **Hardwaretests und Recovery:** Weder ein gesicherter Prüfstand
   noch ein nachweislich erfolgreicher Rückfall-/Wiederherstellungsweg
   für einen missglückten Flashvorgang liegen vor.

**Release-Status:** `safe_to_flash=False`. Eine an den Scooter
auszugebende oder per OTA/seriell zu übertragende Modifikationsdatei
wird nicht bereitgestellt. Die Originaldateien bleiben unverändert.

## Tests

```powershell
$env:MI5PRO_FIRMWARE_DIR = "C:\Users\dzirl\bw-patcher\originale"
poetry run python -m pytest tests/test_mi5pro_mcu_candidate_in_memory.py -q -p no:faulthandler
poetry run python -m pytest tests/test_mi5pro_dual_candidate_in_memory.py -q -p no:faulthandler
```

Beide Testzeilen sind inzwischen erfolgreich ausgeführt worden. Diese
Offline-Ergebnisse sind ausdrücklich **keine Hardwareprüfung oder
Freigabe für den Scooter**.
