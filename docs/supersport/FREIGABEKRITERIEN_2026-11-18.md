# Mi5Pro Super-Sport: Freigabekriterien nach der Offline-Analyse

Stand: 18. November 2026. Das ist eine technische **Sperrliste**, keine
Bauanleitung fuer eine installierbare 30-km/h-Firmware und keine Aufforderung
zu unkontrollierten Versuchen am fahrenden Fahrzeug.

## Nachgewiesene Softwarebasis

- Der Nutzer hat exakt die untersuchte MCU `0007` und BLE `2.7.0_0015`
  mit den SHA-256-Werten aus `bwpatcher.ssm_firmware.ORIGINALS` vorliegen.
- Das Xiaomi-Cloud-OTA-Paket enthaelt einen bitidentischen BLE-Hauptcontainer
  und einen 1338-Byte-Anhang mit Modellkennung und zwei PEM-Zertifikaten.
  Die Hersteller-Signaturakzeptanz ist nicht nachgewiesen.
- Die vorhandenen BLE-/MCU-Ausfuehrungsproben, Status- und Bremspfadanalysen
  betreffen **unveraenderten Originalcode**, teilweise mit synthetischem RAM
  oder nachgebildeten Peripherieantworten.
- Aktueller kompletter Windows-Testlauf: 403 bestanden, eine
  Capstone-`pkg_resources`-Warnung; `-p no:faulthandler` wegen
  dokumentiertem Unicorn-Windows-Konflikt.
- Die Freigabepruefung meldet absichtlich weiterhin
  `release_ready=false` und `flashable_ssm_image_available=false`.

## Offene Integration – am Computer zu erforschen

| Voraussetzung | Noch fehlender belastbarer Beleg |
| --- | --- |
| Firmwareformat | Gesamtes Updatepaket, Zertifikats-/Signaturkette und Geraeteakzeptanz |
| BLE-Codeintegration | Belegter freier Ausfuehrungsspeicher, private RAM-Reserve, echter Kontextvertrag (Stack, IRQ, FPU, Timing) |
| Aktivierung | Explizite Absicht ausserhalb normaler drei Moduswechsel, ohne OEM-Tastenfunktionen zu uebernehmen |
| BLE/MCU-Protokoll | Bestaetigter Ist-Zustand statt bloss zurueckgemeldetem angefordertem Modus |
| Geschwindigkeitsregelung | Vollstaendiger Weg bis Motor-/Stromregelung, korrekt kalibrierte Einheiten, nachgewiesene Grenzen |
| Sicherheit | Urspruengliche Brems-, Fehlermodus-, Akku-/Temperatur- und Schutzpfade auch bei Zustandswechseln |

**Kein einzelner Grenzwertschreibzugriff belegt diese Punkte.** Die originale
Modus- und Reglerwahl begrenzt weiterhin den Zielwert; der beobachtete Status
quittiert keine zusaetzlich angewendete 30-km/h-Grenze.

## Ohne reale Hardware nicht abschliessbar

1. Exakte Identifikation der Diagnosepins, Masse, Spannungspegel und
   galvanischer Rahmenbedingungen. **Kein blindes Anschliessen** des Adapters.
2. Ein nachgewiesener, geraetespezifischer Rueckfall- und Wiederherstellungsweg
   durch qualifiziertes Personal, bevor irgendwelche Schreibversuche stattfinden.
3. Belastbare Messungen am gesicherten Pruefstand, mit pruefbarer
   Notabschaltung, statt unbeaufsichtigter Fahrversuche: Bremsen, Motortemperatur,
   Akku-/BMS-Schutz, Strombegrenzungen, Schaltvorgaenge, Kommunikationsausfall.
4. Nachweis, dass das Zielgeraet ein geaendertes, korrekt authentifiziertes
   Update technisch akzeptiert. Echte Signaturen duerfen nicht behauptet oder
   durch bloss passende Hash- oder CRC-Werte ersetzt werden.

## Aktueller Beschluss

**Keine SSM-Firmware erstellen oder zum Flashen freigeben**, solange die obigen
Integrations- und Hardwarebelege fehlen. Ein Gruen bei Offline-Tests beweist
nur die jeweils konkret getesteten Eigenschaften. Der Scooter ist im
Originalzustand belassen worden.
