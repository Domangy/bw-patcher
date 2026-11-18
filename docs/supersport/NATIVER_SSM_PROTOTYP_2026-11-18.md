# Mi5Pro: nativer Super-Sport-Prototyp, nicht flashbar

**Stand: 18. November 2026.** Branch `codex/mi5pro-ssm-integration`.

Dieses Experiment führt **neuen ARM-Thumb-Maschinencode** in Emulatoren
mit exakt der vorhandenen Original-Firmware BLE `2.7.0_0015` und
MCU `0007` aus. Es erweitert damit die früheren reinen
Python-Zustandstests. Der gewünschte *grundsätzliche* Ablauf ist nachgewiesen,
jedoch **nur im Emulator, nicht auf einem Xiaomi Scooter 5 Pro**.

## Beobachteter Ablauf in echter Thumb-Ausführung (Unicorn)

| Schritt | BLE-OEM-Ereignis | BLE-interner Zustand | Originaler lokaler Modus | BLE-UART-Frame | MCU-Zielwert |
| --- | --- | --- | --- | --- | ---: |
| Anfang | keines | aus | Sport 3 | 51 10 07 23 ... | 417 (~20 km/h) |
| 1. Doppelklick | 2 | Zähler 1 | Walk 11 | normal | Original |
| 2. Doppelklick | 2 | Zähler 2 | Drive 2 | normal | Original |
| 3. Doppelklick | 2 | aktiv | Sport 3 | 51 10 07 24 ... | 627 (~30 km/h) |
| 4. Doppelklick | 2 | aus | Sport 3 | 51 10 07 23 ... | 417 (~20 km/h) |

Die beiden Zahlen sind geräteinterne Rohwerte bei der **synthetischen**
Seriennummernregion `60556`. Die Umrechnung beruht auf dem
rekonstruierten Faktor ca. 20,9 Rohschritte pro km/h. Weder ein
tatsächliches Tempo noch Motordrehzahl, Leistung oder Bremswirkung sind
am Fahrzeug gemessen.

Bei der ersten Folge führt echter originaler BLE-Code drei ursprüngliche
Moduswechsel aus (Sport→Walk→Drive→Sport). Der vierte Doppelklick geht
nicht mehr in die OEM-Moduswechselroutine. Das ist durch einen
Instruktions-Hook auf der originalen `APP+0x80aa`-Funktion nachgeprüft.

Die 12 Byte langen UART-Daten entstehen **innerhalb der emulierten,
modifizierten BLE-Instruktionen**, nicht durch eine nachträgliche
Python-Umschreibung. Die Übertragung zwischen den beiden unabhängigen
Emulatoren erfolgt weiterhin nur durch den Testtreiber; echte
UART-Pegel, Zeitverhalten und Quittung wurden nicht gemessen.

## Neu implementierte Dateien

- `bwpatcher/mi5pro_thumb_hook_experimental.py`: Der originale
  4-Byte-Thumb-Aufruf APP+`0x8550` wird im Emulator auf 98 Bytes
  neuen Thumb-Code an APP+`0x2be62` umgeleitet. Dort werden drei
  getrennte OEM-Doppelklicks, ein synthetischer Zeitabstand von 600
  bis 1600 ms, eine synthetische Zulassungsflagge und die Rückkehr durch
  den nächsten Doppelklick behandelt.
- Zweiter BLE-Redirect bei APP+`0x3ab8`: 32 Bytes zusätzlicher
  Thumb-Code an APP+`0x2bec4` prüfen den internen Aktiv-Zustand.
  Ausschliesslich beim ursprünglichen Sport-UART-Frame `0x23`
  wird im Emulator das Modusbyte auf `0x24` gesetzt und die
  Prüfsumme aktualisiert. Der originale UART-Aufruf läuft danach.
- `bwpatcher/mi5pro_mcu_hook_experimental.py`: Die originale
  MCU-Mode-Selection wird an Dateioffset `0x1d0d6` (Laufzeit
  `0x3856`) in einem Emulator um einen Thumb-Umweg ergänzt.
  Für die vorgeschlagene Sonderkennung Mode 4 schreibt neuer Code
  den Rohwert 627. Für die untersuchten Originalmodi 11, 2 und 3
  ergeben sich dieselben Zielwerte wie zuvor. Der **Mode-4-Zweig
  überspringt ausdrücklich die ursprüngliche Sport-Limit-Klammer**;
  dessen sichere Wirkung auf den vollständigen Motorregler ist
  nicht geprüft.
- `bwpatcher/mi5pro_ssm_native_prototype.py`: Zwei Emulatoren und
  die Übertragung des Byte-Frames **ohne reale Gerätekommunikation**.
- `tests/test_mi5pro_ssm_native_prototype.py`: Rückwärtskompatibilität
  der untersuchten Modi, Aktivierung, Deaktivierung, Wiederaktivierung,
  nicht zulässige Ausgangslage, zu grosse Zeitlücken und Negativfälle.

## Warum dies keine installierbare Firmware ist

1. **Ausführbarer MCU-Speicher:** Die neue MCU-Routine liegt ausschliesslich
   auf einer zusätzlich *im Emulator* angelegten Flash-Seite bei `0xf000`.
   In der echten Firmware ist dieser Bereich weder vorhanden noch
   vom OEM-Bootloader initialisiert. Der neue Routinecode liegt
   **nicht in einem flashbaren MCU-Image**.
2. **BLE-Speicherbesitz:** Der 130-Byte-Nullbereich im entpackten BLE-APP
   und die zehn Bytes bei BLE-RAM `0x20b000` sind nur Kandidaten.
   Andere Firmwareaufgaben können diese Bytes benötigen. Es gibt
   keinen Beweis für freien, ausführbaren Speicher, sichere
   Schreibrechte, Stack-/IRQ-Konformität oder erlaubten Linkerplatz.
3. **Zeitbasis und Sicherheit:** Der 10-ms-Zähler und das
   Zulassungsflag werden vom Python-Testtreiber geschrieben.
   Die tatsächlichen Scooter-Werte für Stillstand, Bremse, Gasfreigabe,
   Fehler, Sperre und Ausschalten sind **noch nicht verbunden**.
   Ausserdem setzt dieser Experiment-Hook die Folge nach anderen
   OEM-Tastenereignissen nicht vollständig zurück. Diese Punkte
   müssen vor einem echten Einsatz fail-safe implementiert werden.
4. **MCU-Protokoll und Regler:** Der Sondermodus 4 wird vom
   ursprünglichen MCU-Feldkonsumenten als Byte übernommen. Seine
   Behandlung durch alle anderen MCU-Dienste ist ungeprüft.
   Es gibt keine authentifizierte Freigabe/Quittung des neuen Limits,
   keine nachgewiesenen Grenzen für Strom, Motor, Temperatur, BMS,
   Bremsen und Rekuperation bei 30 km/h. Die Mode-4-Grenzwahl ist
   **kein Beleg für die tatsächliche Fahrtgeschwindigkeit**.
5. **Geräteupdate:** Der OEM-Boot-/OTA-Prozess, mögliche
   Signatur-/Versionsprüfungen und ein verifizierter
   Wiederherstellungsweg für einen fehlgeschlagenen Flashvorgang
   sind nicht geklärt. Die vorhandene experimentelle BLE-Rekompression
   beweist lediglich eine korrekte Dekodierung im Test.

**Daher bleibt die Firmware-Export- und Flash-Sperre aktiv.**
Es wird weder eine `.bin`-Datei zum Installieren erzeugt
noch das echte Gerät beschrieben. Der Rohcode ist als Nachweis
für eine spätere sichere Integration gedacht.

## Ausführen

Nur mit den exakten Originaldateien; kein Scooter muss angeschlossen sein:

```powershell
$env:MI5PRO_FIRMWARE_DIR = "C:\Users\dzirl\bw-patcher\originale"
poetry run python -m pytest tests/test_mi5pro_ssm_native_prototype.py -q -p no:faulthandler
```

Eine grüne Emulatorprüfung gibt den realen Controller weiterhin nicht frei.
