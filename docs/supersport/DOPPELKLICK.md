# Aktivierung durch drei getrennte OEM-Doppelklicks

Stand: 14. Oktober 2026. Fortsetzung von Draft-PR #1 nach Commit `6062bd2`.
Diese Spezifikation ersetzt die bisherige Fünffachklick-Aktivierung.
**SSM bleibt eine Offline-Simulation; Firmwareexport und Flashen bleiben gesperrt.**

## 1. Zuerst geprüfte Originalereignisse

Die unveränderten Originale MCU `0007` und BLE `2.7.0_0015` sind weiterhin
über die vollständigen Hashes aus [BERICHT.md](BERICHT.md) identifiziert.
Am entpackten APP wurden zuerst sechs Tastendrücke ausgeführt: acht Aufrufe
GPIO-Pegel 1, acht Aufrufe Pegel 0 je Druck, danach 60 Aufrufe Pegel 0.

| Eingabe am originalen Klassifikator | Ausgabe `(Aufruf, OEM-Code)` |
| --- | --- |
| Sechs gleichmässige schnelle Drücke | `(25,2), (57,2), (73,5), (89,2)` |
| Drei Paare, zusätzlich 20 Ruheaufrufe zwischen Paaren | `(25,2), (77,2), (113,5), (129,2)` |
| Drei Paare, zusätzlich 60 Ruheaufrufe zwischen Paaren | `(25,2), (117,2), (209,2)` |

Damit ergeben schnelle sechs Drücke zwar drei Doppelereignisse, aber auch ein
OEM-Fünferereignis. Dieses darf nicht ignoriert oder in SSM umgedeutet werden.
Eine einfache konfliktfreie Alternative im geprüften Originalcode sind drei
**getrennte Doppelklickpaare**. Zwischen den Paaren muss der ursprüngliche
Mehrfachklickzustand auslaufen. Zusätzlich geprüft wurden Paarpausen von
40, 50, 80 und 120 Aufrufen; auch sie liefern hier ausschliesslich `2,2,2`.
Das sind synthetische GPIO-Verläufe, keine Messungen realer Finger/Taster.

Der rekonstruierte Timer ist nominal 10 ms. Beim konservativen Beispiel mit
60 zusätzlichen Ruheaufrufen liegen zwischen den Doppelereignissen jeweils
920 nominale Millisekunden. Zwischen Loslassen des zweiten Drucks und dem
nächsten Paar liegen hier 680 nominale Millisekunden. Bedienvorschlag:
innerhalb eines Paares zügig doppelklicken, danach ungefähr 0,6–0,7 s pausieren.
Die tatsächliche elektrische Polarität, Entprellung und Zeitbasis müssen am
Gerät bestätigt werden.

## 2. Originalverteiler statt neuer Roh-Tastenerkennung

Zusätzlich zum ursprünglichen Klassifikator läuft nun der originale
Aktionsverteiler APP+`0x82d4` mit GPIO-Eingaben, seinen Originalprüfungen und
der tatsächlichen Moduswechselroutine APP+`0x80aa`. Startzustand ist der
synthetisch initialisierte eingeschaltete Sportmodus; Fahrzeugdaten sind sonst
gezielt nullinitialisiert. Logging APP+`0x100b4` und der Speicherauftrag
APP+`0xa150` werden abgefangen. Weder NVM-Schreiben noch der gesamte RTOS-/
Boot-/Funkstack werden dadurch geprüft.

Der Verteiler liefert bei den getrennten Paaren:

| Aufruf | Ereignis | Lokaler Istmodus nach Originalaktion | Anzeige-Bitmap |
| ---: | ---: | --- | ---: |
| 25 | 2 | Fussgänger `11` | 1 |
| 117 | 2 | Drive `2` | 2 |
| 209 | 2 | Sport `3` | 4 |

Auch Start in Drive und Fussgänger durchläuft die drei normalen Wechsel und
kehrt zum jeweiligen Startmodus zurück. Bei unveränderter Originalreihenfolge
startet man die Aktivierung deshalb im **normalen Sportmodus**. Nach drei
Wechseln muss wieder Sport vorliegen. SSM setzt keinen Sollmodus voraus und
springt nicht automatisch aus einem anderen Fahrmodus nach Sport.

Ein zusätzlicher Integrationstest übergibt nach jeder dieser Originalaktionen
den tatsächlichen Modus an den originalen BLE-Framebuilder und anschliessend
an den originalen MCU-Feldkonsumenten. Erst dessen Ergebnis wird als Quittung
an die Python-Simulation gegeben. Das ist ein durchgehender Offline-Vergleich
beider Originale; kein vollständiger Empfangsparser und keine vom echten
Motorcontroller empfangene Quittung.

## 3. Neue Ereignissimulation und Zeitfenster

`ButtonRecognizer`, Rohpegel-Entprellung und Fünffachklick-Aktivierung wurden
aus der SSM-Simulation entfernt. `sample(now, event, inputs, ...)` verarbeitet
einmalig zugestellte OEM-Codes. `None`/0 bedeuten kein Ereignis; boolesche
Rohpegel werden ausdrücklich abgewiesen. Der originale Klassifikator bleibt
eine separat ausführbare, unveränderte Firmwarefunktion.

| Entwurfsparameter | Wert / Wirkung |
| --- | --- |
| Mindestabstand zweier Doppelereignisse | 600 ms; zu schnelle Ereignisse starten die SSM-Zählung neu, ihre normale OEM-Aktion bleibt erhalten |
| Maximalabstand zweier Doppelereignisse | 1600 ms |
| Gesamtfenster | 4000 ms ab erstem Doppelereignis; abgelaufene Folgen werden verworfen |
| Frist für Modusabschluss | 500 ms nach jeder angeforderten OEM-Modusaktion |
| Bestätigter Stillstand | mindestens 500 ms, anschliessend während der ganzen Aktivierungsfolge |

Diese Werte sind konfigurierbare Software-Entwurfswerte. Sie sind nicht als
Herstellerkonstanten oder hardwarevalidierte Bedienzeiten auszugeben.
Die Simulation fügt Einzel-/Doppelklicks kein neues Rohklick-Wartefenster hinzu.
Die normale OEM-Erkennung behält ihre eigene Latenz.

Jedes normale Doppelereignis wird als `NEXT_MODE` an die **ursprüngliche
Aktionsentscheidung samt deren Bedingungen** delegiert. Das ist keine Erlaubnis,
die Moduswechselroutine ungeprüft direkt aufzurufen. Der Modelladapter erhält
ein `ModeRequest` mit Ticket und erwartetem normalen Folgemodus. Nach der
wirklichen Originalaktion muss er ein neues `Inputs`-Snapshot und dieses Ticket
als `mode_ack` liefern. Der Zielwert darf nicht einfach als Istwert kopiert werden.

Für SSM müssen alle drei Originalaktionen abgeschlossen und die dritte
innerhalb der Frist ausdrücklich als tatsächlicher Sportmodus bestätigt sein.
Ein vorher schon angezeigtes Sport, ein unverändert gebliebenes Modusbyte,
eine fehlende/verspätete/falsche Quittung oder ein fremdes Ticket aktiviert nicht.
Ein Sicherheits-/Dashboard-/Tastenereignis im selben Aufruf hat Vorrang.

Aktivierung erfordert Betrieb, gültige bekannte Telemetrie, gemessene
Geschwindigkeit exakt null, bestätigten Stillstand, losgelassenes Gas, keine
Fehler, keine Sperre und ausdrücklich ausgeschlossenen reservierten OEM-Kontext
(`oem_reserved=False`). Unbekannte Werte sperren SSM. Der neue Kontext ist ein
Adaptervertrag, noch kein vollständig rekonstruiertes Firmwarefeld.
Einzel-, Langdruck-, Fünfer-, Freigabe- und unbekannte OEM-Ereignisse unterbrechen
die Folge und werden weitergegeben. Eine Verletzung der Freigaben verwirft
ebenfalls die gesamte bisherige Zählung.

## 4. Anzeige, Deaktivierung und Neustart

Nach bestätigter Aktivierung fordert das Modell 30 km/h an und zeigt logisch
alle drei Symbole dauerhaft. Die belegten separaten Displaybits können ein
späteres Overlay tragen; ihre reale elektrische Wirkung bleibt ungemessen.
Geschwindigkeit, Batterie, Licht, Bluetooth, Warnungen und unbekannte Anzeigefelder
werden vom logischen Overlay nicht verändert.

Ein Doppelereignis in SSM wird im gewöhnlichen, nicht reservierten OEM-Kontext
zur Deaktivierung verwendet und löst **keinen normalen Moduszyklus** aus.
Im bestätigten Stillstand bei tatsächlichem Sportmodus erfolgt die Rückkehr
sofort. Der Override wird `None`: Delegation an den unveränderten normalen
Sport-/Regionswert, für das Zielgerät laut Auftrag 20 km/h. Der Bericht behauptet
weiterhin keinen aus der Hardware unabhängig ausgelesenen Schweizer Grenzwert.

Während Bewegung bleibt die bisherige Sicherheitsentscheidung erhalten:
Deaktivierung vormerken und erst nach bestätigtem Stillstand abschliessen.
Es wird kein Bremsbefehl erzeugt. Wenn der Modus unerwartet nicht mehr Sport
ist, bleibt die Rückkehr vorgemerkt; das Modell kann im sicheren Stillstand
eine logische `RESTORE_SPORT`-Anforderung ausgeben. Ein passender tatsächlicher
Sportzustand ist vor Abschluss nötig. Dafür existiert noch kein freigegebener
Firmwareadapter. Originale Fehlerabschaltung und Schutzreaktionen haben Vorrang
vor jedem SSM-Modellwert, auch solange die Rückkehr vorgemerkt ist.

Reservierte OEM-Kombinationen werden auch in SSM nicht abgefangen. Reset,
Ausschalten und Neustart verwerfen Aktivierung, Vormerkung, Zähler und offene
Modusanforderungen. Es gibt keine Persistenz des SSM-Zustands. Vor einem neuen
Istmodus-Snapshot zeigt die Simulation nach Reset keine erfundenen Modussymbole.

## 5. Was nachweislich erhalten bleibt

| Originalfunktion | Nachweis / Grenze |
| --- | --- |
| Einzelklick/Licht | Originalverteiler plus ursprünglicher Lichtpfad ausgeführt. Zwei Einzelklicks schalten im emulierten GPIO-Ausgaberegister `0x40001000` Bit 6 ein und aus; übrige Portbits und Fahrmodus bleiben erhalten. Kein elektrischer Scheinwerfertest. |
| Normaler Doppelklick | Originalverteiler ruft nach seinen Prüfungen APP+`0x80aa` auf; alle drei Startmodi und ein voller Zyklus sind geprüft. Kein neuer Aufschub des normalen Doppelereignisses durch die SSM-Zählung. |
| Bestehende Modussperre | Setzen des original geprüften Bytes `INFO+0x10` unterbindet im Originalverteiler sämtliche drei Moduswechsel trotz Code 2. Die vollständige Bedeutung dieses Bytes wird nicht neu behauptet. |
| Langdruck/Fünfer/OEM-Resetkontext | Klassifikator unverändert; Langdruckcodes weiterhin original ausgeführt. Simulation delegiert Codes 3/4/5/6/7 und unbekannte Codes und verwirft SSM-Zählung. Der gesamte reale Reset-/Ausschaltablauf wurde nicht gemessen. |
| Modustransport | Originaler BLE-Builder und MCU-Feldkonsument erhalten dieselben skalaren Normalmodi. Die Anzeige-Bitmap 7 wird nicht als Motor-Modus 7 verwendet. |
| Strom, Rekuperation, Bremse, Temperatur, Schutz | Keine Änderungen an diesen Firmwarebereichen, Parametern oder bestehenden Patcherklassen. Originaldateihashes bleiben identisch. Ein Funktionstest dieser Schutzpfade auf Hardware ist damit nicht ersetzt. |
| Exportsperre | Vollständige CLI-/GUI-/Mischpatchtests bestehen; weiterhin kein SSM-Patcher und keine flashbare SSM-Ausgabe. |

Die Emulation erlaubt beim Originalverteiler zusätzlich ausschliesslich das
bekannte vier Byte breite GPIO-Ausgaberegister im emulierten Speicher. Sie
öffnet kein reales Gerät. Sonstige unbekannte Peripherieschreibzugriffe brechen
weiterhin ab. Code, RAM und Peripheriemodell bleiben voneinander getrennt.

## 6. Vereinfachung und verbliebene Grenzen der Firmwareintegration

Die OEM-Erkennung kann unverändert bleiben; eine konkurrierende Rohgestenerkennung
und das Zurückhalten der ersten beiden normalen Moduswechsel entfallen.
Neu maschinell belegt ist APP+`0x8550`, Laufzeit `0x00816550`: ein vollständiges
vier Byte langes `BL` auf APP+`0x80aa`, Fortsetzung APP+`0x8554`. Es liegt hinter
den ursprünglichen Doppelklickprüfungen und im komprimierten Block `0xf5c7`.
Nach der Originalroutine liegt der lokale Istmodus bei `0x20826d` vor.

Ein späterer Adapter könnte die bestehende Routine zunächst ausführen und erst
danach einen bestätigten normalen Sportmodus für die SSM-Anforderung nutzen.
Zur SSM-Deaktivierung müsste er am selben Pfad den normalen Moduszyklus gezielt
auslassen. Andere OEM-Ereignisse/Resetkontexte müssen die Zählung weiter abbrechen
können; nur Doppelaufrufe an dieser Stelle zu zählen reicht dafür nicht aus.
APP+`0x82fc` bleibt eine mögliche Beobachtungsstelle für den gesamten Ereignisstrom.

Es gibt jetzt **fünf semantisch belegte Hook-Kandidaten**, weiterhin null zur
Injektion freigegebene Stellen. Offen bleiben ausführbarer Platz, private RAM-
Reservierung, vollständige Kontext-/Register-/Interrupt-Verträge, unveränderte
Update-/Vertrauensanforderungen und eine sichere zusätzliche Begrenzungsumschaltung.
Der BLE-Modus allein ist noch keine echte Motorcontroller-Quittung: Transport,
Antwort, Telemetriefrische und der zusätzliche SSM-Zustand müssen integriert werden.

Nur OEM-Endereignisse enthalten ausserdem keinen garantierten Beginn eines
Tastendrucks. Zeitliche Überschneidungen mit Fehler-/Rückkehrzuständen brauchen
im echten Adapter eine definierte Ereignisordnung und einen validierten Vertrag;
die frühere Rohpegel-Simulation wird dafür nicht als Nachweis weiterverwendet.

Hardware bleibt zwingend für reale Taster-/Schedulerzeiten, UART-Pegel und
Rückmeldungen, dauerhafte gemeinsame Piktogrammanzeige samt Warnpriorität sowie
Strom-/Temperatur-/Brems-/Schutz- und App-Verhalten. Die neue Kombination reduziert
die Gestenprobleme; sie beweist noch keine sichere 30-km/h-Integration.

## 7. Reproduktion und vollständige Tests

```bash
poetry install --with research
python -m bwpatcher.mi5pro_emulator --ble /lokal/originale/ble_2.7.0_0015.bin --mcu /lokal/originale/mcu_0007.bin
python -m bwpatcher.ssm_demo
MI5PRO_FIRMWARE_DIR=/lokal/originale python -m pytest tests -q
```

Aktuell **219 bestanden, 0 fehlgeschlagen, 0 übersprungen** mit beiden Originalen.
Ohne Originale: **172 bestanden, 47 ausdrücklich übersprungen**. Enthalten sind
107 Ereignis-/Zustandsfälle, 65 Container-/Originalcodefälle, 44 Audit-/Exportfälle
und drei GUI-/Demofälle. Die bekannte Capstone-`pkg_resources`-Warnung bleibt.
Die Demo simuliert ihre Modusquittungen ausdrücklich; die Originaltests beziehen
sie aus ausgeführtem Originalcode. Keine der beiden Prüfarten ist ein Hardwaretest.

Aktuelle strukturierte Nachweise stehen in [BEFUNDE.json](BEFUNDE.json).
Entwicklungsstufe bleibt 3, kein integrierter SSM-Firmware-Patch und keine
Umgehung von Sicherheitsmechanismen.
