# Mi5Pro: BLE-Tastenpfad bis MCU (Offline-End-to-End-Test)

Stand: 18.11.2026. Entwicklungsbranch `codex/mi5pro-ssm-integration`.

## Nachgewiesenes Originalverhalten

Mit den exakt identifizierten Originalen BLE `2.7.0_0015` und MCU `0007`
ist ein isolierter Tastentest durchgeführt worden. Der ursprüngliche
BLE-Tastenverteiler erzeugt bei sechs Einzelklicks mit jeweils
60 zusätzlichen 10-ms-Ticks Pause zwischen den Doppelklickpaaren:

| Original-Tick | Nominale Zeit | OEM-Ereignis | Ursprünglicher Modus |
| ---: | ---: | ---: | --- |
| 25 | 250 ms | 2 | 11 (Fussgänger) |
| 117 | 1170 ms | 2 | 2 (Drive) |
| 209 | 2090 ms | 2 | 3 (Sport) |

Das ist **Originalcode im Emulator**, nicht Hardware. Die 10-ms-Intervalle
sind aus dem untersuchten Original übernommen, nicht am Gerät gemessen.

`bwpatcher.mi5pro_end_to_end` verknüpft diesen Original-Trace mit der
abstrakten Super-Sport-Zustandsmaschine, dem originalen BLE-Modusframe
`51/10/07` und dem originalen MCU-Feldkonsumenten. Die Original-MCU-Grenzwahl
wird nur für den im Forschungsbericht bereits untersuchten synthetischen
Seriennummernpräfix `60556` ausgeführt. Es gibt keine Schreiboperation
auf einem realen Gerät.

## Beweisgrenzen der Integration

- Drei originale Doppelklickereignisse und die ursprünglichen Moduswechsel
  können ohne Änderung am Scooter nachvollzogen werden.
- Die unabhängige Aktivierungsabsicht ist im Modell nur eine **synthetisch
  erteilte Demo-Freigabe**. Im realen BLE-Code existiert noch keine geprüfte
  Bedienhandlung dafür.
- Die Modell-Quittungen sind **synthetische Tickets**, keine echten
  MCU-Quittungen. Die bekannten Statusframes enthalten weder
  Request-Tickets noch den sicher bestätigten angewendeten Motorgrenzwert.
- Nach dem dritten Doppelklick verwendet der ausgeführte Original-MCU-Code
  weiterhin den **unveränderten Sport-Grenzwert**. Die virtuelle Anforderung
  `30 km/h` greift NICHT in den realen Regler ein.
- Es wurde weder ein Firmware-Patch noch ein Hersteller-signiertes Paket
  erstellt. Die Testdatei ist **nicht flashbar**.

Ein öffentlich dokumentierter DFU-Datenpfad für den Scooter 5 Pro existiert:
[KuziaMother/SCOOTER_5_PRO](https://github.com/KuziaMother/SCOOTER_5_PRO),
`core/dreame_flasher.py`. Ein Übertragungsprotokoll allein beweist jedoch
nicht, dass der Bootloader eine modifizierte Firmware akzeptiert oder ein
umgebauter Controller die Brems-/Temperatur-/Batterieschutzfunktionen erhält.

## Reproduktion der neuen Regressionstests

Die Originaldateien bleiben ausserhalb des Git-Repositories. Unter Windows
mit der bisherigen Poetry-Umgebung und verbundenem Laptop:

```powershell
cd C:\Users\dzirl\bw-patcher-ssm-integration
$env:MI5PRO_FIRMWARE_DIR = 'C:\Users\dzirl\bw-patcher\originale'
poetry install --with research
poetry run python -m pytest tests/test_mi5pro_end_to_end.py -q -p no:faulthandler
poetry run python -m bwpatcher.mi5pro_end_to_end --ble "$env:MI5PRO_FIRMWARE_DIR\ble_2.7.0_0015.bin" --mcu "$env:MI5PRO_FIRMWARE_DIR\mcu_0007.bin" --demo-intent
```

Diese zusätzlichen Tests wurden nach Erstellung des Branches **noch nicht
ausgeführt**, weil die Desktop-Verbindung unterbrochen wurde. Vor jeglichem
Merge sind ihre tatsächlichen Ergebnisse zu prüfen. Der bereits vor der
Unterbrechung erfolgreich ausgeführte reine Tastentest zeigte die drei oben
dokumentierten OEM-Ereignisse.

## Fehlende Punkte vor einer möglichen Hardwarefreigabe

1. Eine eindeutig absichtliche, sichere Aktivierung, die nicht mit drei
   gewöhnlichen Moduswechseln verwechselt werden kann.
2. Nachgewiesene BLE-Code-/RAM-Integration mit Stack-, Interrupt- und
   Watchdog-Verträglichkeit, ohne OEM-Funktionen zu überschreiben.
3. Eine eigenständige, fail-safe MCU-Grenzzustandsregelung, deren Wirkung
   über die gesamte Brems- und Motorreglerkette und bei Datenverlust
   nachvollzogen ist.
4. Physische Prüfung von Bremse, Gas, BMS, Temperatur, Fehlerfall,
   Display, Neustart und gültigem Rückfall unter geeigneten Prüfbedingungen.
5. Nachweis von Integrität, Signatur-/Bootloader-Kompatibilität,
   Recovery-Verfahren und der tatsächlichen Geräteakzeptanz.
6. Erst dann ein separat freigegebener und geprüfter Firmwareexport.

**Keiner dieser offenen Punkte wird durch eine bestandene Emulation ersetzt.**
