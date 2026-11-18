# Mi5Pro: Binäre Firmwareintegration und reale Blocker (18.11.2026)

## 1. Externe MCU-Patchdatei geprüft

Forschungsquelle: https://github.com/KuziaMother/SCOOTER_5_PRO
lokal geprüfter Upstream-Stand `1d1b1dd` (18.11.2026),
`research/custom_mcu/patched_mi5pro_firmware.bin`.

| Datei | Grösse | SHA-256 |
|---|---:|---|
| unser Original MCU `0007` | 149'504 | `ddcd65400c4fbdb45cb4cdbec2e812026d7bc6cb755fd9dd0180800caed5f9b8` |
| externes Patch-Paket | 150'841 | `00b8fb7b85dcbe7b5bf9974de24b40472cb4e6ada26718d56fbab06c556d3f01` |

Die ersten 149'504 Bytes unterscheiden sich in **16 Byte an 7
zusammenhängenden Änderungsstellen**. Zwei sind die berechneten Prüfsummen
bei Dateioffset `0x0a..0x0b` und `0x19830..0x19831`. Die anderen
Änderungen liegen im MCU-Grenzwahlbereich, darunter
`0x1d0e9..0x1d0f1` (ursprüngliche Instruktionen durch Thumb-NOPs ersetzt),
`0x1d141` und `0x1d2f0..0x1d2f3`. Das Paket hat 1337 zusätzliche
Bytes hinter dem Originalbereich.

**Dieser statische Vergleich beweist weder 30 km/h noch Boot- oder
Fahrsicherheit.** Besonders der Ersatz der Originalbegrenzungsprüfung ist
kein akzeptabler Bestandteil eines separat nachgewiesenen, fehlertoleranten
Super-Sport-Modus. Die externe Datei wird nicht ins eigene Repository kopiert
und nicht für Nutzerfreigabe oder Flashen vorgesehen.

## 2. BLE-Container in Arbeit

Im Modul `bwpatcher.mi5pro_ble_repack_experimental` ist eine
**reine In-Memory-Rekompression** des erkannten BLE-APP programmiert:

- Original BLE und APP werden mit den bekannten SHA-256-Hashes identifiziert.
- Der komprimierte APP wird als 12 LZMA-Blöcke im bestehenden Containerformat
  erzeugt; Header-Länge, SHA-256 und innerer Image-Digest werden neu
  berechnet. Der ROM-Patch-Container bleibt unverändert.
- Das neue Image kann mit dem bestehenden strikten Offline-Decoder wieder
  geprüft werden; eine synthetische Byteänderung bleibt beim Rücklesen erhalten.
- Ein unbekanntes Original, geänderte Image-Header und geänderte APP-Längen
  werden abgewiesen.

**Wesentliche technische Grenze:** Der Originalhersteller verwendet
LZMA-alone-Streams mit explizit gespeicherter unkomprimierter Länge.
Python-libLZMA produziert bei Neu-Kompression Streams mit unbekannter Länge
(`ffffffffffffffff`) und EOS-Marker. Beide Formate können lokal
dekodiert werden, aber die Bytefolgen und die Gesamtlängen sind verschieden.
Die ursprüngliche Firmware auf dem Gerät muss dieses alternative
Blockformat nicht akzeptieren. Der umgebende Xiaomi-OTA-Anhang und dessen
eventuelle Hersteller-Signaturprüfung sind ebenfalls nicht rekonstruiert.

Daher **keine CLI-, GUI- oder Exportmöglichkeit** für neu komprimierte
Images. Der einzige Testpfad arbeitet mit Bytes im RAM. Ein
strukturell korrektes Binärpaket ist ausdrücklich keine freigegebene
Firmware für reale Hardware.

## 3. Was noch für den gewünschten Modus fehlt

1. Eindeutiger BLE-Programm-Hook für drei getrennte OEM-Doppelklicks
   mit **separater, absichtlicher Freigabe** statt versehentlichen normalen
   Moduswechseln; belegte sichere Speicher-/Stack-/IRQ-Grenzen.
2. Vom Originalmodus getrennter MCU-Reglerzustand, dessen obere Grenze bei
   unveränderten Schutzfunktionen und Ausfällen sicher zurückfällt.
3. Echt erkennbarer angewendeter Reglerzustand (nicht nur UART-Modusecho).
4. Reproduzierbare OEM-kompatible Verpackung bzw. Geräte-Akzeptanz,
   inklusive sicherer Wiederherstellung, **vor** einem Schreibversuch.
5. Echte Prüfstandsversuche an Bremse, Gasanforderung, BMS, Temperatur,
   Motorsteuerung und Software-Neustart.

Kein vorhandenes Werkzeug erfüllt aktuell diese fünf Bedingungen.
Die 20-km/h-Originalsteuerung und die OEM-Images bleiben unverändert.
Die Offline-Ergebnisse sind **keine Freigabe zum Flashen**.
