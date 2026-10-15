# Mi5Pro: Bremsabsicht, Reglerpfad und belastbare Analysegrenzen

Stand: 15. Oktober 2026. Fortsetzung von Commit `f940ba7` im bestehenden
Draft-PR #1. Die Ausgangsbefunde bleiben in [INTEGRATION.md](INTEGRATION.md)
erhalten. Dieser Bericht ergänzt neue Nachweise; Containerentpackung und
bereits geklärte Tasten-/Displaypfade wurden nicht erneut untersucht.

**Ergebnis:** Der Bremswert ist vom originalen Dashboard-ADC-Feld bis in einen
originalen MCU-Bremszweig verfolgt. Er kann als zusätzliche Bedienbedingung
untersucht werden, beweist allein aber keine Aktivierungsabsicht. Die vollständige
Originalfunktion für Grenzwahl und Geschwindigkeitsregelung ist offline
ausgeführt. Auswahlgrenze, Regler-Sollwert, Reglerausgang und Modusecho sind
verschiedene Zustände. Es gibt keinen validierten zusätzlichen SSM-Grenzzustand.
Unbekannte Motorperipherie wird nicht durch erfundene Werte ersetzt.

## 1. Methode und neue Werkzeuge

`bwpatcher.mi5pro_constraints` ergänzt die vorhandenen Emulatoren um
Lese-/Ausführungsspuren, Analogverarbeitung, abgefangene Diagnose-/Taskaufträge
und ausdrücklich abbrechende Peripherieproben. Ausgabe ist nur JSON, keine
Firmware. Exakte Originalhashes sind vor Adressauswertung/Emulation erforderlich:

| Original | SHA-256 |
| --- | --- |
| MCU 0007, 149504 Bytes | `ddcd65400c4fbdb45cb4cdbec2e812026d7bc6cb755fd9dd0180800caed5f9b8` |
| BLE 2.7.0_0015, 152552 Bytes | `061d34cac06fb31d93ff8f47650cd09d61fa46e7a883b35c23f35cabff1e6df7` |

APP-Adressen sind Offsets im entpackten BLE-APP, Laufzeitbasis `0x0080e000`.
MCU-Dateioffsets beziehen sich auf die gesamte Datei; der untersuchte innere
MCU-Code beginnt bei Datei+`0x19880`. Originalcode bleibt unverändert RX.
Synthetischer RAM und isolierte Aufrufreihenfolgen sind keine Live-Messungen.

Reproduzierbare Ergebnisse: [GRENZEN_BEFUNDE.json](GRENZEN_BEFUNDE.json).
Originale, abgeleitete Images und SDK-Dateien liegen ausserhalb des Repositorys.

## 2. Priorität 1: vorhandene Bremsinformation

### Nachgewiesener Datenweg

Der Diagnosepfad APP+`0x684a` liest `u16[0x2085c2]`, nennt den Wert im Original
`LINETEST_BRAKE_STATE_GET` und gibt ihn Big Endian an APP+`0x6328` mit Opcode
`0xe9`, Länge 2. Im Test wird nur dieser Sendeauftrag abgefangen; eine
Diagnoseverbindung oder Übertragung findet nicht statt.

Der Analogpfad APP+`0x74ac` liest ADC-Kanäle, APP+`0x7582` filtert Werte.
Statisch nachvollzogen ist die getrennte Ablage: Gas bei `0x2085c0`, Bremse
bei `0x2085c2`. ADC-MMIO, Float-Konvertierung und vollständiger IRQ-Ablauf
wurden hier nicht neu emuliert. Die folgenden Nachweise starten ausdrücklich
mit synthetischen Werten in diesen gefilterten RAM-Feldern.

APP+`0x75fa` berechnet bei gesetztem Betriebsbyte `INFO+0x1d=1` aus beiden
Werten je einen Prozentwert. Im untersuchten ADC-Testbereich 0–4095 lautet
die Abbildung `min(100, floor(max(raw-900,0)*100/1550))`. Das Original enthält
zusätzlich eine Byte-Verengung; diese Formel ist keine Behauptung für beliebige
16-Bit-Werte oder physische Spannungen. Beispiele:

| Brems-RAM roh | Originaler Bremswert | Stelle im Original-TX | MCU-RAM |
| ---: | ---: | --- | --- |
| 600 / 900 / 901 | 0 | Framebyte 7 | `0x20000234` |
| 916 | 1 | Framebyte 7 | `0x20000234` |
| 1400 | 32 | Framebyte 7 | `0x20000234` |
| 2449 | 99 | Framebyte 7 | `0x20000234` |
| 3000 | 100 | Framebyte 7 | `0x20000234` |

Dashboard-Ziel ist `INFO+0x16 = 0x208282`; Gas liegt daneben bei `0x208281`
und auf Framebyte 6. Der originale Builder APP+`0x3940` erzeugt den
`51/10/07`-Frame mit Summe. Das MCU-Originalfragment
`[Datei+0x203b2, Datei+0x20502)` übernimmt die Werte nach `0x20000233/234`
und begrenzt auf 100. Das Fragment setzt den aus dem Prolog bekannten R4=0
synthetisch voraus; es ist kein vollständiger UART-/IRQ-Empfangstest.

Die **vollständige** Originalfunktion Datei+`0x1c234` verarbeitet den Bremswert:
`u32[0x2000041c] = (brake << 15) / 100`. Auf dem geprüften Ausgangspfad
setzen positive Werte die Bytes `0x20000262/263`. Das zweite beeinflusst
später den originalen Geschwindigkeitsreglerzweig. Physische Bremskraft,
Rekuperation oder Motorabschaltung sind damit nicht gemessen.

### Warum der Wert noch keine sichere Aktivierungsfreigabe ist

- APP+`0x75fa` prüft das ADC-Bereitschaftsbyte `0x2085cc` selbst nicht.
  Im Test erzeugt auch Bereitschaft=0 denselben Wert 32 aus dem alten RAM-Wert
  1400. Ein Bereitschaftsflag ist ausserdem noch kein Sample-Zeitstempel.
- Bei `INFO+0x2c=0x15` wird der übertragene Bremswert null, obwohl der rohe
  Bremswert 1400 bleibt. Ein konkreter ursprünglicher Erzeuger ist jetzt
  ausgeführt: APP+`0x7922` setzt bei Rohwerten ≤100 oder ≥3200 nach 401
  isolierten Aufrufen Analogzustand 6 (`INFO+0x18`). APP+`0x6fe8` aggregiert
  daraus `INFO+0x2c=0x15`; APP+`0x75fa` unterdrückt den Bremswert. Die
  Grenzwerte 100/101 und 3199/3200 sind geprüft. Bei Rohwert 4095 fällt der
  normalisierte Wert dabei von 100 auf 0. Das ist keine gemessene Zeitdauer,
  elektrische Fehlerreaktion oder vollständige Erklärung aller Statuscodes.
  Null im normalisierten Feld darf nicht als Beweis „Bremse losgelassen“
  oder „Sensor gültig“ verwendet werden.
- Drei normale Fahrmoduswechsel sind auch bei gezogener Bremse möglich.
  Die Originalausführung liefert für synthetische Bremswerte 600, 1400 und
  1600 dieselben Ereignisse `2,2,2` und dieselben Modi `11,2,3`. Eine blosse
  Bremspegel-Bedingung unterscheidet die Absicht deshalb nicht zuverlässig.

Ein denkbarer zusätzlicher Bedienvertrag wäre eine zuvor bestätigte Freigabe,
ein bewusstes neues Bremsbetätigungsereignis mit losgelassenem Gas, stabilem
Stillstand und frischen gültigen Samples während der drei OEM-Doppelklicks.
Auch eine Bremsflanke beweist für sich keine Absicht: Sie kommt im normalen
Betrieb vor. Der Bedienvertrag muss bewusst gewählt und auf Konflikte geprüft
werden. Es werden keine Schwellen, Haltezeiten oder neuen Tastencodes als
fertige Gerätelösung ausgegeben.

Die unabhängige einmalige Modellfreigabe aus `f940ba7` bleibt daher bestehen.
Es wird **keine automatische Freigabe aus Bremswerten** ergänzt. Das bewahrt
die normale Bedienung und vermeidet die Behauptung eines unbewiesenen Adapters.

### OEM-Sonderkombinationen erhalten

APP+`0xb6a2`, vom ursprünglichen Langlang-Ereignispfad aufgerufen, wertet beide
Analogwerte aus. Nur bei Gas **und** Bremse jeweils >1400, Geschwindigkeit
null, nicht gesetzter Sperre und ungesetztem Update-/Sondergate erreicht
der geprüfte Pfad den ursprünglichen Aufruf APP+`0xb492`. Die Originalmeldung
dazu lautet `finish abs zb reset`; seine vollständige Resetwirkung wird
nicht behauptet. Im Test wird der Resetkörper abgefangen.

Grenztests 1400/1401, Gas/Bremse einzeln, Bewegung und Sperre bestätigen die
ursprüngliche Entscheidung. Der OEM-Fünferpfad verwendet ebenfalls den
Gaswert. Deshalb bleiben OEM-Klassifikator, Sondercodes und Prioritäten
unangetastet; Bremse/Gas werden weder umgeschrieben noch zurückgehalten.
Ein späterer Adapter muss reservierte Kontexte vor jeder SSM-Zählung ausschliessen.

## 3. Priorität 2: weiterer Geschwindigkeitsbegrenzungspfad

Neu ausgeführt wird die **gesamte** Originalfunktion
`[Datei+0x1d078, Datei+0x1d2da)`, einschliesslich Softwaredivision und
Reglerarithmetik. Sie braucht in diesen Szenarien kein MMIO und keine Stubs.
Der frühere Test prüfte nur das Grenzauswahlfragment.

| Stufe | Originalquelle / Ziel | Nachweis |
| --- | --- | --- |
| Geschwindigkeitseingang | Flag `0x20000100`, Periodenwert `0x20000158`; Hilfsroutine Datei+`0x1d874` | Flag=0 liefert 0; sonst Softwaredivision `48000 / period`, anschliessende Filter |
| Gemeldete Geschwindigkeit | `0x20000236` | Berechnung aus einem Filterausgang, getrennt vom Reglerausgang; physische Einheit weiterhin unkalibriert |
| Gewählte Grenze | `0x2000177c` | Originale Modus-/Präfixwahl und zusätzlicher Vergleich bei Datei+`0x1d0ec` ausgeführt |
| Interner Sollwert | `0x200003f2` | Zusätzliche Zustands-/Rampenlogik beeinflusst Aktualisierung; kein blosser Alias der gewählten Grenze |
| Tatsächlich gelesener Sollwert im geprüften Reglerzweig | Lesen bei Datei+`0x1d1e4` aus `0x200003f2` | Lesehaken belegt den Zugriff auf dem zweiten Rechenschritt, keine aus Sollwerten erzeugte ACK |
| Reglerausgang | `0x2000042c`, Kopie `0x20001780` | Originalfunktion berechnet/schreibt beide; Werte sind keine Geschwindigkeiten in km/h |

Alle 16 Modusnibbles wurden mit der vollständigen Routine geprüft: 11 →125,
2 →Drivewert, 3 →Sportwert, alle übrigen →208, jeweils unter dem unveränderten
Vergleich. Ein unbenutzter Moduscode eröffnet keinen vierten Geschwindigkeitszustand.
Der hier geprüfte Präfix `60556` liefert weiterhin Drive=313, Sport=417.

Bei Originalflag `0x20000333=1` und unverändertem Modus hält der Regler einen
bereits vorhandenen Sollwert zunächst fest. Aus synthetisch gesetztem Sollwert
200 wird erst im siebten Aufruf 201, obwohl die Auswahlgrenze in jedem Aufruf
417 ist. Ein normaler Drive-/Sportwechsel aktualisiert den Sollwert über einen
anderen Zweig sofort. Folgerung: Ein zusätzlicher SSM-Unterzustand bei
weiterhin gemeldetem Sport muss diese Rampen-/Moduszustände berücksichtigen.
Ein einzelner zusätzlicher Grenzschreibzugriff wäre kein vollständiger Übergang.

Der Regler arbeitet phasenweise. Beim geprüften ersten Aufruf ist der Sollwert
noch nicht im PI-Zweig gelesen, beim zweiten schon. Mit synthetischen
Referenzwerten 5000 beträgt der Ausgang 5000, während gemeldete Geschwindigkeit
null und Auswahlgrenze 417 bleiben. Diese Grössen dürfen nicht gleichgesetzt
werden. Das Werkzeug erfindet insbesondere **keine Verbindung** vom Reglerausgang
zur gemeinsamen FOC-Eingangsreferenz `0x20000224`.

Nach dem originalen Bremsaufruf mit Bremswert 32 ist `0x20000263=1`;
die vollständige Reglerfunktion nimmt ihren vorhandenen Brems-/Referenzzweig,
liest dort den Geschwindigkeits-Sollwert nicht und liefert im geprüften
initialisierten Szenario Ausgang null. Die Grenze bleibt 417. Das belegt eine
unveränderte Zweigpriorität, keine vollständige Schutzprüfung unter Last.

**Zusätzlicher Zustand ohne entfernten Vergleich:** Ein neuer Zustand muss
unter der unveränderten Semantik weiterhin innerhalb der ursprünglichen
Sportobergrenze liegen. Falls diese dem normalen Zielwert 20 km/h entspricht,
kann ein zusätzlicher Moduscode allein keine höhere 30-km/h-Grenze freigeben.
Eine Trennung von normalem Sportziel und zusätzlicher zulässiger Obergrenze
wäre eine neue, noch zu belegende Regelstrategie. Den Vergleich stehen zu lassen,
aber seine Schutzbedeutung ungeprüft zu verändern, wäre kein Sicherheitsnachweis.
Kein solcher Patch wurde entwickelt; Originalgrenzen und NVM bleiben unverändert.

Der gesamte Datenweg bis Stromregelung/PWM/Motor ist weiterhin **nicht**
geschlossen. Statisch ist ein weiterer Verbraucher von `0x20001780` bei
Datei+`0x1b86a` sichtbar, mit weiteren Begrenzungen und Zustandszweigen. Die
Motorpfade brauchen jedoch unbekannte Peripherie; siehe Abschnitt 5.

## 4. Priorität 3: Speicher, Stack und Hook-Kontexte

Eine neue Originalausführung von APP+`0x2546` erfasst den Aufruf an ROM
`0x269d0`: Handleziel `0x2081a4`, Name `app`, Einstieg `APP+0x2447` mit
Thumbbit, Parameter 0, Stackargumente **8192 und 1**.

Der bereits verwendete öffentliche SDK-Spiegel enthält am fixierten Stand
`f80ae6a2362d986a3d69c764ca1cda3ec39155c5`:

- [ROM-Symbole](https://github.com/GeFengthe/RTL8762/blob/f80ae6a2362d986a3d69c764ca1cda3ec39155c5/bin/rom_symbol_iar.icf): `os_task_create = 0x000269d1`.
- [os_task.h](https://github.com/GeFengthe/RTL8762/blob/f80ae6a2362d986a3d69c764ca1cda3ec39155c5/inc/os/os_task.h): fünftes Argument `stack_size` ausdrücklich in **Bytes**, sechstes `priority`.

Damit ist ein ursprünglicher **Auftrag über 8192 Byte App-Taskstack mit
Priorität 1** durch Aufrufargumente und passende SDK-Signatur belegt.
Der ROM-Körper wird im Emulator nur durch Rückkehr ersetzt. Tatsächlicher
Allokationserfolg, Adresse, Belegung, freier Rest und ROM-Patchverhalten sind
nicht geprüft. Aus 8192 darf weder eine freie Reserve von 8192 noch ein
zulässiger SSM-Speicherbereich abgeleitet werden. Unbekannter ROM-Code bleibt
gesperrt; ein weiterer Aufruf in der gemappten Stubseite wird nicht freigegeben.

Die neue Referenzsuche findet den Thumb-Funktionszeiger auf Timerhandler
APP+`0x9e18` in APP+`0xc384` und dessen direkten Aufruf des Tastenverteilers
bei APP+`0x9e2a`. Weitere direkte Kandidaten: `0x613e →0x60f4` und
`0x6180 →0xc6b2`. Die Halbwortsuche ist bewusst konservativ: Daten können
Instruktionen ähneln, abgeleitete/unalignierte Zeiger und Laufzeitregistrierung
bleiben offen. Fehlende Treffer beweisen keine fehlenden Einsprünge.

| Kontextanforderung | Stand |
| --- | --- |
| Fünf vollständige Originalinstruktionen, Fortsetzung, ausgewählte R0–R12/SP/LR/APSR/ITSTATE | Bereits in `f940ba7` belegt; unverändert |
| MCU-SP der vollständigen Grenz-/Reglerfunktion | Neu beobachtet bis `0x20001b74`, also 52 Byte unter dem initialen SP; nur diese isolierten Pfade |
| App-Taskstackauftrag | Neu 8192 Byte, kein beobachteter Wasserstand |
| Tatsächlicher Task-/IRQ-Stackbesitz und Heapreserve | Offen; kein privater SSM-RAM reserviert |
| Vollständige Registerlebensdauer und alle eingehenden Pfade | Offen; Referenzkandidaten sind kein vollständiger CFG |
| FPU und Ausnahmezustand | Originaler Timeraufrufpfad enthält FPU-Code, etwa APP+`0x9898` mit D8–D11-Sicherung; keine vollständige FPU-/Lazy-Stacking-/Interruptemulation |
| MSP/PSP, Privilegien, Masken, Reentranz, Sperren, atomare Zustandsveröffentlichung | Offen; statischer Funktions-ABI-Nachweis reicht für einen Hook im Funktionskörper nicht |
| Maximale Laufzeit/Interruptverschachtelung | Nur auf Hardware belastbar messbar; Instruktionsbudget und beobachteter SP sind keine Maximalwerte |

Alle fünf Hook-Kandidaten bleiben zur Injektion gesperrt. Es gibt weiterhin
keinen Linkerplatz, keinen nachgewiesenen privaten Stack-/Heapbereich und
keine geprüfte zusätzliche SSM-Ausführung im Originalkontext.

## 5. Priorität 4: angewendeter Reglerzustand und Messgrenze

Neuer Gegenbeweis: Zwei Originalausführungen mit gleichem Modus Sport,
gleicher Auswahlgrenze 417 und gleicher gemeldeter Geschwindigkeit null
haben interne Sollwerte **200 beziehungsweise 417**. Beide erzeugen exakt
`61300a23008800190100000000609e`. Schon der tatsächlich vorliegende interne
Sollwert ist damit aus dem bisherigen Statusframe nicht bestimmbar.

Eine unabhängige Diagnose müsste mindestens gemeinsam beobachten:
Auswahlgrenze `0x2000177c`, internen Sollwert `0x200003f2`, nachgewiesenen
Lese-/Rechenschritt, Reglerausgänge `0x2000042c/1780`, relevante Brems-/Fehler-
und Zustandsflags sowie eine echte Zeit-/Bootgeneration. Ein RAM-Snapshot
ohne Kontext ist noch kein Beleg, dass der Motor diesen Zustand verwendet.
Ein ursprünglicher UART-Befehl mit diesem vollständigen Vertrag ist nicht
identifiziert. Es wird kein erfundenes ACK- oder Diagnoseprotokoll eingebaut.

Zwei gezielte Originalproben markieren die nächste Grenze. Nach ursprünglicher
Initialisierung, Präfixauswahl `60556`, Sport und zwei isolierten Regleraufrufen:

| Einstieg | Erster nicht modellierter Zugriff im geprüften Pfad |
| --- | --- |
| MCU-Datei+`0x1b67c` | Lesen `0x40012c54` bei Datei+`0x1c7e2` |
| MCU-Datei+`0x1a938` | Lesen `0x40012c54` bei Datei+`0x1be20` |

Ohne diesen aktivierten Ausgangszustand kann der erste Pfad auch einfach
zurückkehren. Ein solcher inaktiver Durchlauf beweist keine Gesamtabdeckung.
Die neuen Werkzeuge stoppen am unbekannten Zugriff und setzen weder Register
noch Timerbits auf passende Werte. Timer-/ADC-/Motorreaktion, IRQ-Ordnung und
Lastzustand dürfen nicht aus einem erfundenen Peripheriemodell bestätigt werden.

Für den aktuellen Stand endet hier die verlässliche Integrationsaussage.
Weiteres Lesen einzelner Softwarepfade bleibt möglich; ein sicherer
geschlossener Motorregelkreis lässt sich mit den vorhandenen Dateien und
isolierten Emulatoren allein nicht validieren.

## 6. Tests, Erhalt und Reproduktion

```bash
poetry install --with research
python -m bwpatcher.mi5pro_constraints --ble /lokal/originale/ble_2.7.0_0015.bin --mcu /lokal/originale/mcu_0007.bin
MI5PRO_FIRMWARE_DIR=/lokal/originale python -m pytest tests/test_mi5pro_constraints.py -q
MI5PRO_FIRMWARE_DIR=/lokal/originale python -m pytest tests -q
# Ohne lokale Originale:
python -m pytest tests -q
```

Neu sind **68 gezielte Fälle**, davon 54 mit Originalen. Der vollständige
Lauf umfasst **384 bestanden, 0 fehlgeschlagen, 0 übersprungen** mit Originalen;
ohne Originale **233 bestanden, 151 ausdrücklich übersprungen**. Die bestehende
Capstone-`pkg_resources`-Warnung bleibt. Es gibt keine Hardwaretests.

Die vollständige Suite umfasst auch die bereits bestehenden Tasten-/Licht-,
Modus-, Sonderereignis-, Rückkehr-, Neustart-, Anzeige- und Exportprüfungen.
Die neu belegten Brems-/Reglerzweige laufen ausschliesslich im Originalcode;
kein ADC-Wert oder Bremsbefehl wird für SSM auf einem Gerät verändert. Keine
Modifikation an Motorstrom-, Brems-, Rekuperations-, Temperatur- oder
Batterieschutzpfaden, NVM, bestehenden Patcherklassen oder Updateprüfungen.
Originalhashes bleiben gleich. Unverändertheit ist kein Ersatz für Schutztests
unter Last.

## 7. Gelöst, softwareseitig offen, Hardware erforderlich

**Softwareseitig gelöst:** Herkunft und Transport des Bremswerts bis in einen
Original-Bremszweig; Abgrenzung des normalisierten Nullwerts; ausgewählte
OEM-Sondergates; gesamte Grenz-/Reglerfunktion in den geprüften Szenarien;
Unterschied zwischen Auswahlgrenze, Sollwert, Rechenphase und Ausgang;
zusätzlicher Gegenbeweis zur Status-ACK-Annahme; App-Taskstackauftrag.

**Softwareseitig offen:** vollständige Quellen/Frische der Sicherheitsdaten,
ein bewusst gewählter Aktivierungsvertrag samt reservierten Kontexten,
zusätzlicher Grenzzustand unter allen unveränderten Schutzprioritäten,
vollständige Datenfluss-/Schedulerverknüpfung bis zum Motor, vollständiger
CFG-/FPU-/IRQ-/Reentranzvertrag, private Speicherreservierung und
vertrauenskonforme spätere Integration. Eine Bremsbedingung ist noch keine
implementierte Gerätelösung. Keine Hook-Freigabe.

**Zwingende Hardwaremessungen:**

1. Tatsächliche Gas-/Brems-ADC-Werte bei losgelassenem/betätigtem Hebel,
   Signalrichtung, Fehlerfälle, Filter-/Samplezeiten und Frische messen.
   OEM-Reset-/Langdruckkombinationen und normale Moduswechsel passiv erfassen.
2. Beide UART-Richtungen synchron zu Hebelbewegung und Reglertakt aufnehmen;
   Verlust, Duplikate, Reset, Zeitbasis und Felder mit RAM-Zuständen korrelieren.
   Das bekannte Modusecho allein reicht dafür nicht.
3. Über einen vorhandenen erlaubten Diagnose-/Debugzugang Reglerzustände,
   Timer-/ADC-Status und Ausführungsreihenfolge beobachten; keine Entsperrung
   und keine Umgehung von Sicherheitsmechanismen. Ist dieser Zugang nicht
   verfügbar, bleibt der unabhängige Reglernachweis gesperrt.
4. Tatsächliche App-/IRQ-Stackbelegung, Wasserstände und Heap-/Stackgrenzen
   bei Funk-, Anzeige-, Brems- und Sonderereignissen messen. Der Stackauftrag
   und die Emulatorspitze ergeben keine garantierte Reserve.
5. Auf kontrolliertem Prüfstand Rohgeschwindigkeit, tatsächliche Reglerwirkung
   und Brems-/Strom-/Rekuperations-/Temperatur-/Batteriepriorität prüfen.
   Displaywirkung und Warnpriorität bleiben zusätzlich hardwarepflichtig.

Keine dieser Messungen wurde ausgeführt. Entwicklungsstufe 3 bleibt bestehen.
**SSM-Exportsperre aktiv; keine flashbare SSM-Firmware und kein Flashvorgang.**
