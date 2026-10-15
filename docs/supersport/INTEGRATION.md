# Mi5Pro: Speicher, Hook-Kontexte und Controller-Rückkanal

Stand: 15. Oktober 2026. Fortsetzung von Draft-PR #1, Ausgangsstand
`f0109c0db3b6168a2e6e015b75b660f0787374aa`. Verwendet werden ausschliesslich
die unveränderten Originale MCU `0007` und BLE `2.7.0_0015`; Hashes und
Adresskonventionen stehen in [FORTSETZUNG.md](FORTSETZUNG.md#1-identität-und-beweisgrenzen).
Die neuen maschinenlesbaren Ergebnisse stehen in
[INTEGRATION_BEFUNDE.json](INTEGRATION_BEFUNDE.json).

**Ergebnis:** Die ursprüngliche RAM-Initialisierung, die Auswahl der regionalen
Fahrgrenzen und ein original erzeugter und original empfangener Status-Rückkanal
sind offline rekonstruiert. Der Status meldet den empfangenen Modus, bestätigt
aber keine angewendete Geschwindigkeitsgrenze. Deshalb wird daraus keine
SSM-Freigabe abgeleitet. Es gibt weiterhin keinen integrierten Firmware-Patch,
keinen reservierten SSM-Speicher und keinen zur Injektion freigegebenen Hook.
Die Exportsperre bleibt bestehen; kein Flashvorgang wurde ausgeführt.

## 1. Neue Werkzeuge und Reichweite

`bwpatcher.mi5pro_integration` ergänzt die vorhandenen Emulatoren. Alle
Codeadressen verlangen exakt passende SHA-256-Hashes. Originalcode bleibt
lesbar/ausführbar und wird nicht verändert. Unbekannter Code, unbekannte
Speicherzugriffe und erschöpfte Instruktionsbudgets brechen die Untersuchung ab.
Ausgabe ist ausschliesslich JSON. Es gibt weder eine serielle Schnittstelle
noch BLE-Gerätezugriffe, einen Linker oder eine Firmwareausgabe.

- BLE: ursprüngliche Initialisierungstabellen ausgewertet; ROM-Kopie und
  BSS-Löschung anhand ihrer Parameter **modelliert**, ROM-Instruktionen nicht
  ausgeführt. Einzelne APP-Funktionen laufen mit diesem Datenzustand.
- MCU: ursprüngliche Scatter-Dekompression und Nullinitialisierung tatsächlich
  ausgeführt. Vollständige ausgewählte Funktionen prüfen R4–R11 und
  Stackausgleich; ausdrücklich begrenzte Fragmente haben synthetisch gesetzte
  Eingangsregister. Unbekannte MMIO-Zugriffe sind nicht zugelassen.
- Kein vollständiger Boot-, IRQ-, RTOS-, UART- oder Funklauf. Zeitwerte und
  synthetische RAM-Zustände sind keine Messungen am Gerät. Die Tests verknüpfen
  Originalroutinen, stellen aber keine reale Kommunikation mit einem Controller her.

## 2. Speicherbelegung und Initialisierung

### BLE-APP

APP+`0x4dc`, aufgerufen aus dem Startpfad bei APP+`0x5dc`, enthält die
Initialisierung. APP-Offsets schliessen den 1024-Byte-Header ein;
Laufzeitadresse = `0x0080e000 + APP-Offset`.

| Zweck | APP-Quelle | RAM-Bereich, Ende exklusiv | Bytes |
| --- | --- | --- | ---: |
| Erste ROM-Kopie | `0x2bff4` | `0x207c00–0x207d24` | `0x124` |
| Zweite ROM-Kopie | `0x2c118` | `0x207d24–0x208178` | `0x454` |
| BSS-Löschung | keine | `0x208178–0x20bd80` | `0x3c08` |

Damit sind `0x4180` Bytes initialisierter zusammenhängender Speicher bekannt.
Der erste kopierte Bereich enthält zur RAM-Ausführung übersetzte IRQ-Stubs.
PC-relative Sprünge dort müssen an der RAM-Ladeadresse interpretiert werden;
eine Disassemblierung an der APP-Quelladresse ergibt irreführende Ziele.
Dieser Bereich ist kein Codeplatz für SSM.

Die Kopie verwendet ROM `0x59e9a`, die Löschung ROM `0x5a01c`.
Weitere Abschnitte haben Länge null und Basis `0x21c000`. Daraus folgt **keine
freie Lücke**. Kopierte Deskriptoren enthalten `0x20bd80`; Heap-/ROM-Allocator-
und Taskstackbesitz sind nicht vollständig geklärt. Der bisherige Emulator-SP
`0x20fff0` ist eine Modellvorgabe, keine aus dem Original bestätigte
Stackreservierung. Auch der minimale beobachtete SP ist keine freie RAM-Grenze.

### MCU-Teilimage

Das ES32-Teilimage liegt in der MCU-Datei in `[0x19880, 0x24710)`, bildet
Laufzeitcode ab Adresse null ab und hat Länge `0xae90`. Vektortabelle und
Startcode setzen SP auf `0x20001ba8`. Die Tabelle bei Datei+`0x24394` enthält:

| Quelladresse im Teilimage | RAM-Ziel | Ausgabelänge | Originalroutine |
| --- | --- | --- | --- |
| `0xab34` | `0x20000000` | `0x838` | Teilimage+`0x9cc`, Datei+`0x1a24c`: Dekompression |
| `0xae90` | `0x20000838` | `0x1370` | Teilimage+`0x83d4`, Datei+`0x21c54`: Nullinitialisierung |

Die zweite Region endet genau am initialen SP. Ihre Aufteilung in globale
Daten und Stackreserve ist damit noch nicht vollständig bekannt. Ein einfacher
Klartext-Datenvergleich hätte die Geschwindigkeitsgrenzen übersehen: Sie liegen
in den tatsächlich dekomprimierten Daten. Die neue Emulation begrenzt sämtliche
RAM-Lese-/Schreibzugriffe auf `[0x20000000, 0x20001ba8)` und mappt kein MMIO.
Für den Statusbuilder beträgt der beobachtete SP `0x20001b18`; daraus folgt
kein globaler Stackbedarf. Es wurde kein SSM-Speicher reserviert.

## 3. Hook-Kandidaten: nachgewiesene Teilverträge

Die Untersuchung zeichnet R0–R12, SP, LR, APSR und ITSTATE vor/nach den
Originalinstruktionen auf. Bestehende Logger-, Speicherauftrags- und
Display-I/O-Stubs zerstören in einer zusätzlichen Variante absichtlich
R1/R2/R3/R12 und NZCVQ-Flags. Das prüft die ausgewählten Pfade unter zulässigem
ABI-Clobbering; die eigentlichen Logger-/NVM-/Displaytreiberroutinen sind damit
weiterhin nicht ausgeführt. Es wird kein Hook injiziert.

| APP-Offset | Original / Fortsetzung | Beobachteter Kontext und Verpflichtung |
| --- | --- | --- |
| `0x8264` | `BL 0x81ce`, danach `0x8268` | SP `0x20ffc0`, R4=0, R5=`0x208624`; R0 wird Phasenereignis. Ursprünglichen Phasenzustand erhalten. |
| `0x82fc` | `BL 0x8260`, danach `0x8300` | SP `0x20ffc8`, R4=`0x20826c`, R5=`0x208624`; R0 wird OEM-Code. Alle Originalereignisse einschliesslich Sonder-/Resetcodes weiter behandeln. |
| `0x8550` | `BL 0x80aa`, danach `0x8554` | SP `0x20ffc8`; R4=`0x20826c`, R5=`0x208624`, R6=`0x2085c0`, R7=`0x320`, R9=`0x2082bc`, R10=1. OEM-Gates liegen davor; lokaler Modus danach bei `0x20826d`. |
| `0x611c` | `STRB.W R0,[R4,#0x60]`, danach `0x6120` | SP `0x20ffe0`, R4=`0x2088b0`, R0=4, R1/R5=`0x208660`. Nur Slot 12 wird geschrieben; Register und Flags bleiben gleich. |
| `0xc76c` | `LDRB.W R0,[R4,#0x60]`, danach `0xc770` | SP `0x20ffc0`, R4=`0x2088b0`; R0 wird 4. Andere Register und Flags bleiben gleich; anschliessende Anzeigeaggregation erhalten. |

SP bezieht sich auf den synthetischen Einstieg `0x20fff0`. In allen geprüften
Paaren ist ITSTATE=0 und SP vor/nach gleich; R4–R11 bleiben bei den drei
BL-Aufrufen erhalten. Kleinster beobachteter BLE-SP ist `0x20ffb0`, also 64
Bytes unter dem gewählten Einstieg. Das ist weder RTOS-Stackbudget noch
Worst-Case-Laufzeit. Die vollständigen Werte stehen im JSON.

LR ist bei BL-Aufrufen aufrufzerstörbar: Nach `0x8264` ist beispielsweise
`0x008161dd` aus einem verschachtelten Aufruf sichtbar, nicht zwingend die
BL-Fortsetzung. Bei `0x8550` lautet LR vorher `0x0081654d`, danach
`0x00816555`. Ein Hook darf keinen erfundenen LR-Erhaltvertrag voraussetzen.
R1 und Flags werden bei diesem Testaufruf tatsächlich zerstört.

Bei den einzelnen STRB-/LDRB-Stellen reicht hingegen die Funktions-ABI nicht:
Auch volatile Live-Register und Flags des laufenden Funktionskörpers müssten
erhalten bleiben. Hinzukommen sämtliche direkten/indirekten Einsprünge,
Reentranz, privilegierter Zustand, MSP/PSP, Interruptmasken, FPU-Kontext,
atomare Veröffentlichung, Stackausrichtung und Rückkehr in jedem Pfad.
Diese vollständigen Verträge sind **noch nicht bewiesen**. Aus fünf semantisch
geeigneten Kandidaten werden weiterhin null freigegebene Einsprünge.

## 4. Originale Geschwindigkeitsbegrenzung

Die ursprüngliche Funktion Datei+`0x1dea4` wählt anhand der ersten fünf
Seriennummerzeichen sieben Tabellenpaare aus. Der Aufrufer bei Datei+`0x1c9ba`
übergibt Daten aus dem NVM-Lesepfad. Tabelle nach Originaldekompression:
RAM `0x2000080c`, 14 kleine 16-Bit-Werte. Zielwerte: Drive `0x20000324`,
Sport `0x20000326`, Auswahlindex `0x200003ca`.

| Präfix im Original | Drive roh | Sport roh |
| --- | ---: | ---: |
| `60550` | 417 | 522 |
| `60555` | 417 | 522 |
| `60556` | 313 | 417 |
| `60557` | 417 | 522 |
| `60561` | 313 | 417 |
| `60564` | 417 | 668 |
| `61143` | 313 | 417 |

Die Präfixe sind keine hier bestätigte Länderzuordnung. Seriennummer/NVM des
Zielgeräts wurden nicht ausgelesen oder geändert. Auch die physische Einheit
der Rohwerte ist nicht kalibriert; eine angenommene Skalierung ist kein
Geschwindigkeitsnachweis. Die Tests setzen nur synthetischen Emulator-RAM.

Der unveränderte Auswahlpfad Datei+`0x1d0c6–0x1d0f2`, R4=`0x20001768`,
schreibt den gewählten Wert nach `0x2000177c`: Fussgänger-Code 11 → 125,
Drive-Code 2 → Drivewert, Sport-Code 3 → Sportwert, unbekannter Code → 208.
Ein vorhandenes Flag `0x20000339=1` wählt zunächst 522. Der zusätzliche
Originalvergleich bei Datei+`0x1d0e8` begrenzt weiterhin auf den Sportwert:
bei Sport=417 bleibt das Ergebnis selbst mit diesem Flag 417; ein synthetischer
Drivewert 1000 wird ebenfalls auf 417 begrenzt.

Eine sichere atomare 30-km/h-Umschaltung ist dadurch **nicht** gefunden.
Die alten Speed-Patches entfernen gerade diesen zusätzlichen Vergleich und
sind kein Integrationsweg. Kein Originalvergleich, keine Strom-, Brems-,
Rekuperations-, Temperatur- oder Batterieschutzfunktion wurde geändert.

## 5. Tatsächlicher Originalcode des Rückkanals

### Framebuilder und Empfang

MCU-Datei+`0x211f8` erzeugt im ursprünglichen Ringpuffer `0x200010b5`
(acht Slots à 150 Bytes, Index `0x200002c9`) einen Statusframe. Das erste
Pufferbyte ist die interne Länge 15 und gehört nicht auf die Leitung:

```
61 30 0a [oberes Nibble | Modus] ... zehn Payloadbytes insgesamt ... SUM 9e
```

Der Frame hat insgesamt 15 Bytes, SUM ist die Summe der ersten 13 Wirebytes
modulo 256. Ein vollständiges erzeugtes Beispiel im initialisierten
Emulatorzustand lautet `61300a23008800190100000000609e`.
Byte 3 enthält Mode aus `0x20000229` und oberes Nibble aus `0x20000228`.
Bytes 9/10 enthalten Geschwindigkeit roh aus `0x20000236`, Big Endian.
Weitere Payloadfelder werden hier nicht als vollständig verstanden ausgegeben.

Der originale BLE-Empfänger APP+`0x4476` verwendet R0=`0x20856a`, gesetztes
16-Bit-Flag bei +2, Längenbyte `0x20869d` und Puffer `0x20869f`. Er prüft
Rahmenlänge, Endbyte und Summe (APP+`0x55ac`), dispatcht `61/30` nach APP+`0x43c4`
und schreibt:

| Bedeutung | BLE-RAM |
| --- | --- |
| zurückgemeldeter Modus | `0x2082d1` |
| zurückgemeldetes oberes Nibble | `0x2082d0` |
| Geschwindigkeit, eventuell für Anzeige angepasst | `0x2082ce` |
| eigener angeforderter Modus, unverändert separat | `0x20826d` |

Neun Kombinationen aus drei normalen Modi und drei oberen Nibbles laufen
durch originalen BLE-TX, MCU-Feldkonsumenten, MCU-Statusbuilder und BLE-RX.
Die Geschwindigkeitsroutine des BLE-Empfängers addiert unter einer Schwelle
bei Rohwerten ab 50 einen Wert 5; Schwelle in `0x20800a`. Das ist keine
bestätigte physische Skalierung. Ein künftiger Sicherheitsadapter müsste
unveränderte Rohtelemetrie und kalibrierte Frische verwenden.

### Warum diese Meldung keine SSM-Quittung ist

1. Die Modusquelle ist das bereits empfangene Anforderungsfeld. Im Test kann
   Sport zurückgemeldet werden, während `0x2000177c` noch den vorher berechneten
   Drivewert 313 enthält. Erst ein weiterer Originalauswahlaufruf ergibt 417.
   Das belegt eine mögliche isolierte Aufrufreihenfolge, keinen gemessenen Scheduler.
2. Mit Originalpräfix `60556` (Sport 417) und `60564` (Sport 668) entstehen
   **vollständig identische Statusframes**. Die angewendete Grenze ist daraus
   nicht bestimmbar. Ein Sportecho beweist insbesondere keine 30 km/h.
3. Es gibt kein Request-Ticket im untersuchten Frame. Wiederholte identische
   Statusframes sind nicht einer bestimmten lokalen Anforderung zuordenbar.
4. Gates `0x20000339` und `0x20000358` können den Sender unterdrücken.
   Senderzustand `0x2000018a` und 64-Bit-Zähler `0x200001e0` wählen Status,
   keine Nachricht oder `61/31/09`. Grenzen 1600/3200 sind Zählereinheiten;
   ihre Frequenz wurde nicht gemessen. Die Modellfrist 500 ms ist keine
   nachgewiesene Zusage dieses Rückkanals.

Der neue lesende `decode_status()` meldet daher ausdrücklich
`confirms_applied_speed_limit=false` und `wire_sequence_number_present=false`.
Das bisherige `ModeRequest`-/`mode_ack`-Ticket bleibt ein abstrakter
Adaptervertrag. Weder ein MCU-Feldschreibzugriff noch dieser Status wird
automatisch als Bestätigung einer angewendeten SSM-Grenze übernommen.

### Erforderliche zusätzliche Framevalidierung

Der Originalempfänger akzeptiert auch den kurzen, summenkorrekten Frame
`61 30 00 91 9e`. Sein `61/30`-Handler liest Felder ausserhalb der deklarierten
Payload aus dem statischen Empfangspuffer; bei nullinitialisiertem Rest ergibt
sich sogar Modus 1 aus dem Summenbyte. Das ist im Originalcode ausgeführt.
Allgemeine Länge/Checksumme allein genügen deshalb nicht als Telemetriebeleg.

Der neue Beobachter verlangt exakt 15 Bytes, Typ `61/30/0a`, Endbyte,
korrekte Summe und bekannte Normalmodus-/Nibblewerte. Er weist dieses Beispiel
und unbekannte Zustände ab. Er verändert den Originalempfänger nicht und ist
noch kein eingebauter Adapter. Kontext-, Reihenfolge-, Frische- und
Fehlerprioritätsprüfungen bleiben zusätzlich erforderlich.

Beim Originalpfad für inkonsistente Rahmenlänge wird ROM `0x5a01c` über
APP+`0x92b0` zum Löschen aufgerufen. Im Emulator ist dort nur die Rückkehr
modelliert (`rom_rx_clear_not_executed`); der ROM-Löschkörper, UART-
Resynchronisation und Folgerahmen sind nicht getestet. Der gültige `61/30`-
Normalpfad benötigt diesen Stub nicht. Prüfungen von Checksumme/Endbyte
laufen ebenfalls ohne diesen ROM-Löschpfad.

## 6. Schutz gegen unbeabsichtigte drei Moduswechsel

Drei gewöhnliche Moduswechsel aus Sport können exakt dieselbe Ereignisfolge,
Zeitabstände und Telemetrie wie die gewünschte Geste erzeugen. Ein Algorithmus
mit ausschliesslich diesen Eingaben kann die Absicht nicht unterscheiden.
Engere Zeitfenster verhindern diesen Konflikt nicht zuverlässig.

Deshalb verlangt das Modell zusätzlich ein **unabhängiges bewusstes
Freigabesignal** über `grant_activation_intent(now)`, bevor die drei OEM-
Doppelklicks zählen. Es wird niemals aus normalen Moduswechseln abgeleitet.
Das ist nur eine lokale Simulations-API; ein authentifizierter Bedienweg am
echten Gerät oder ein neuer Bluetooth-Befehl ist nicht implementiert.
Eine bewusste, authentifizierte App-Freigabe wäre ein zu prüfender Entwurf,
keine bereits verfügbare Xiaomi-Funktion. Eine weitere Tastenkombination wird
wegen der unvollständig bekannten OEM-Sonderkontexte nicht erfunden.

Die einmalige Freigabe gilt im Entwurf 6000 ms, ist nur mit dem gerade
verarbeiteten sicheren Sport-/Stillstandssnapshot erhältlich und setzt die
Zählung zurück. Aktivierung verbraucht sie. Timeout, Sicherheits-/OEM-
Unterbrechung, falscher Modusabschluss, Ausschalten und Reset widerrufen sie.
Nach einer Rückkehr kann die gleiche Folge ohne neue Freigabe nicht reaktivieren.
Die übrigen Stillstands-, Gas-, Fehler-, Sperr- und Drittabschlussbedingungen
bleiben erforderlich. Die realen Quellen dieser vertrauenswürdigen Zustände
sind noch zu integrieren.

Ohne Freigabe führen dieselben drei Doppelklicks unmittelbar zu drei normalen
OEM-Moduswechseln, enden im normalen Sportmodus und erzeugen keinen Override.
Einzelklick/Licht und alle anderen OEM-Aktionen werden weiterhin delegiert.
Die zusätzliche Freigabe verändert im Modell nur die SSM-Zulassung. Der reale
Bedienweg ist eine offene Produkt- und Integrationsentscheidung.

## 7. Vollständige Validierung und Erhalt der Originalfunktionen

```bash
poetry install --with research
python -m bwpatcher.mi5pro_integration --ble /lokal/originale/ble_2.7.0_0015.bin --mcu /lokal/originale/mcu_0007.bin
python -m bwpatcher.ssm_demo
MI5PRO_FIRMWARE_DIR=/lokal/originale python -m pytest tests -q
# Ohne lokale Originale:
python -m pytest tests -q
```

Aktuell **316 bestanden, 0 fehlgeschlagen, 0 übersprungen** mit Originalen.
Ohne Originale **219 bestanden, 97 ausdrücklich übersprungen**. Enthalten sind
128 Zustands-/Ereignisfälle, 65 bisherige Originalforschungsfälle, 76 neue
Integrationsfälle, 44 Audit-/Exportsperrfälle und drei UI-/Demofälle.
Bekannte Capstone-`pkg_resources`-Abkündigungswarnung; keine Hardwaretests.
Die neuen Änderungen rechtfertigen den vollständigen Regressionslauf.

Nachweislich erhalten auf den geprüften Pfaden: originale Einzelklick-
Lichtschaltung im GPIO-Modell, normaler Moduszyklus samt vorhandenem Gate,
unveränderter OEM-Klassifikator, Weiterleitung der Sonderereignisse,
originale Begrenzungsauswahl einschliesslich zusätzlichem Vergleich,
getrennte Modus- und Anzeigefelder und sämtliche Exportverbote. Neustart und
Freigabeentzug sind im Zustandsmodell geprüft. Originalhashes sind identisch.
An Motorstrom, Bremse, Rekuperation, Temperatur und Batterie wurden keine
Firmwarebytes, Parameter oder bestehenden Patcherklassen verändert. Diese
Unverändertheit ersetzt keine Funktionsprüfung der Schutzpfade unter Last.

## 8. Gelöste und offene Hindernisse

| Bereich | Softwareseitig jetzt belegt | Weiter offen |
| --- | --- | --- |
| Speicher | beide Initialisierungsschemata, tatsächliche MCU-Dekompression | Besitzer/Reserve von Heap, Task-/IRQ-Stacks, ausführbare Erweiterung und private SSM-Daten |
| Hooks | Originalinstruktionen, alle allgemeinen Register und ausgewählte Vor-/Nachkontexte | vollständiger Kontrollfluss, alle Zustände, Interrupt-/FPU-/Privileg-/Zeitvertrag, atomarer Adapter |
| Begrenzung | Präfixauswahl und unveränderter zusätzlicher Clamp | tatsächliches Zielgerät-NVM, physische Einheit, sicherer atomarer SSM-Grenzwechsel mit allen Schutzprioritäten |
| Rückkanal | Originalbuilder und APP-Parser, getrenntes Modusecho, Gegenbeispiele zur ACK-Annahme | UART-Erfassung/Frische, tatsächlicher angewendeter Grenzwert, Verlust-/Resetverhalten, kohärenter SSM-Zustandsvertrag |
| Fehlaktivierung | unabhängige einmalige Modellfreigabe verhindert gewöhnliche Moduszyklen ohne Freigabe | sicherer expliziter Freigabeweg auf dem Gerät samt Authentifizierung und Bedienprüfung |

Weitere Softwareanalyse ist weiterhin möglich: vollständige Referenzen,
Allocator-/Taskerzeugung, Fehlerprioritäten und Updatevertrag. Diese Lücken
werden nicht pauschal als nur durch Hardware lösbar bezeichnet. Es existiert
noch kein nachweislich sicherer Injektions- oder 30-km/h-Pfad.

## 9. Konkret notwendige Hardwaremessungen

1. **Identität und Speicher:** tatsächliche Dashboard-/Motorcontroller-PCBs und
   Prozessorrollen bestimmen; Seriennummer/Regions-NVM nur lesen. Heap- und
   Taskstackgrenzen, Stack-Wasserstände unter verschachtelten Interrupts und
   konkurrierenden Funk-/Displayaktionen erfassen. Synthetischer SP und
   statischer Datenbereich liefern diese Reserve nicht.
2. **Passive Kommunikation:** Leitungen und elektrische Pegel identifizieren;
   beide Richtungen mit gemeinsamer Zeitbasis aufzeichnen. Baudrate/Framing,
   `51/10` und `61/30`/`61/31`, Rohgeschwindigkeit, Session-/Sendegates,
   Zeitbasis, Verlust, Duplikate und Resetfolge bestimmen. Noch keine
   zusätzlichen Motorbefehle einspeisen. Modusecho und angewendeten Reglerwert
   getrennt beobachten; Wireecho allein kann Letzteren grundsätzlich nicht beweisen.
3. **Ereignis- und Laufzeitvertrag:** reale Tasterpausen/Prellen, OEM-Langdruck,
   Resetkombinationen, Licht, App-Ereignisse, IRQ-/Task-Reentranz und maximale
   Latenz der Kandidaten messen. Keine feste 500-ms-Quittungsfrist aus den
   Emulatoraufrufen ableiten.
4. **Display:** physische Bits 1/2/4 und gemeinsames dauerhaftes Leuchten prüfen,
   Warn-/Fehlerpriorität, Helligkeit und Treiberstrom messen. Die bisherige
   Byte-Ausgabe allein beweist diese Eigenschaften nicht.
5. **Regler und Schutz:** nach geklärtem Softwarevertrag auf einem kontrollierten
   Prüfstand Rohgeschwindigkeit und originale Grenzwerte kalibrieren, Last-/
   Brems-/Rekuperations-/Temperatur-/Batterieprioritäten und Neustart-/
   Verbindungsverlustübergänge prüfen. Eine spätere 30-km/h-Anforderung benötigt
   zusätzlich einen belegten angewendeten Reglerzustand. Ein Fahrversuch
   ersetzt diese Nachweise nicht.

Keine dieser Messungen wurde hier durchgeführt. Bis zur geklärten Integration
und ausreichenden Validierung bleibt Entwicklungsstufe 3 bestehen; keine
flashbare SSM-Firmware und kein Flashvorgang.
