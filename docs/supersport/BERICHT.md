# Xiaomi Electric Scooter 5 Pro: SuperSport Mode (SSM)

Stand: 14. Oktober 2026. Untersuchte Ausgangscodebasis: `95a8f339787a1fb6486554d61b573b8e2b688c53`.
Zielgerät laut Auftrag: `xiaomi.scooter.5pro`, Schweizer Ausführung,
MCU `0007`, BLE `2.7.0_0015`.

**Aktuelle Aktivierung:** drei getrennte OEM-Doppelklicks mit normalen
Moduswechseln; erst nach bestätigtem dritten Abschluss im Sportmodus SSM.
Die Fünffachklick-Aktivierung ist ersetzt. Einzelheiten und Originalcode-Traces
stehen in [DOPPELKLICK.md](DOPPELKLICK.md).

**Entwicklungsstufe 3 — Simulation erfolgreich.** Die Zustandsmaschine,
schreibgeschützte Originalprüfung, Export-Sperre, Offline-Demo und Tests sind
implementiert. In der [Fortsetzung der Originalanalyse](FORTSETZUNG.md) sind
nun auch das BLE-APP entpackt, Originalroutinen ausgeführt sowie Tasten-,
Display- und Modusübertragungspfade lokalisiert. Ein ausführbarer SSM-Firmware-Patch
und die elektrische
Ansteuerung aller drei Symbole sind **nicht implementiert**. Es gibt keine
Hardwarefreigabe. Es wurde kein Scooter geflasht und keine flashbare
SSM-Datei erzeugt.

## A. Firmwareanalyse und Machbarkeit

### Quellen und Integrität

Die Streamlit-Seite war mit HTTP-Sitzungscookies erreichbar. Ihr öffentliches
Quellprojekt [argusblack/mi-fw-info](https://github.com/argusblack/mi-fw-info)
enthält einen Firmwarekatalog, keine Firmwarebinärdateien. Der geprüfte
[Katalogstand](https://github.com/argusblack/mi-fw-info/blob/ae9260764c863aede29bba8053c1986645e1e07f/mi.json)
ordnet beide Dateien ausdrücklich `xiaomi.scooter.5pro` zu. Die Oberfläche
bezeichnet den Hauptdownload als BLE-Firmware. Die Binärdateien wurden über
HTTPS direkt vom dort verlinkten Xiaomi-CDN `fk-res-abroad-cdn.home.mi.com`
bezogen, ausschliesslich ausserhalb dieses Git-Repositories gespeichert und
gegen die Katalog-MD5-Werte geprüft.

| Komponente | Katalogversion | Bytes | MD5, Download und Katalog identisch |
| --- | --- | ---: | --- |
| MCU | `0007` | 149504 | `aabaad0de541d7c79ca24d28c45ba097` |
| BLE | `2.7.0_0015` | 152552 | `1c76ba994d8326dca0203a424dc09ff6` |

SHA-256 der vollständig heruntergeladenen Dateien:

```text
MCU ddcd65400c4fbdb45cb4cdbec2e812026d7bc6cb755fd9dd0180800caed5f9b8
BLE 061d34cac06fb31d93ff8f47650cd09d61fa46e7a883b35c23f35cabff1e6df7
```

Diese Kombination aus Katalogzuordnung, Hersteller-CDN, Längen und Hashes ist
die Grundlage der Originalidentifikation. Sie ersetzt keine verifizierte
Herstellersignatur. Die Schweizer Region lässt sich daraus nicht bestätigen;
Regionseinstellungen können im Gerätezustand/NVM liegen. Insbesondere wird
aus dem Vorhandensein eines 25-km/h-Wertes im Code keine Schweizer
Originalgeschwindigkeit abgeleitet.

### Projektarchitektur

`bwpatcher/modules/mi5pro.py` erbt von `ES32Patcher` und dieser von
`CorePatcher`. Keystone assembliert ARM-Thumb-Anweisungen; Capstone liest
Thumb-Code in Little Endian. Das genaue Siliziummodell und alle
Peripherieregister wurden nicht identifiziert.

Die anderen Modellfamilien verwenden unter anderem `LKS32Patcher` und
`CoreN32Patcher`. Die N32-/LEQI-Pfade besitzen eigene Entpackungs-, XOR-,
CRC- und Ausgabeabläufe. Sie dürfen nicht auf die Mi5Pro-BLE-Datei übertragen
werden. Auch die UART-/Padding-Patches anderer Modelle sind keine Belege für
entsprechende Mi5Pro-Hooks. Insbesondere retuniert Ultra4 bei manchen
Speed-Patches auch Modusströme; diese Implementierung ist für den Auftrag
ungeeignet und wird nicht verwendet.

`detect.py` erkennt Modelle anhand der ersten `0x80` Bytes. Das Mi5Pro-Original
wird anhand der Kennung `000700010001` bei `0x22` korrekt erkannt. Diese
heuristische Modellerkennung prüft weder den gesamten Dateiinhalt noch dessen
Hardwarekompatibilität. Die neue Originalprüfung verlangt deshalb den exakten
SHA-256-Hash. Eine Datei mit nachgebautem Header und gültiger CRC wird nicht
als untersuchtes Original akzeptiert.

`utils.patch_firmware()` lädt die Patcherklasse dynamisch, führt die angeforderten
Methoden aus und liefert deren Daten zurück. Die bisherigen Ausgabewege sind
CLI-Datei und Streamlit-Download. Im älteren CLI-Pfad können gewöhnliche
Patchfehler gesammelt und dennoch Daten zurückgegeben werden. Die neue
SSM-Sperre liegt deshalb **vor** Instanziierung und erster Änderung und wird
auch im CLI ausdrücklich als Fehler behandelt.

Das ursprüngliche Repository enthält keine implementierte Mi5Pro-Tastengesten-
oder Segmentanzeigesteuerung. Es enthält auch keine belastbare BLE-Entpackung
für diese Datei. `find_pattern()` liefert den ersten Treffer und hat keine
allgemeine Eindeutigkeitsprüfung. Ein einzelner Pattern-Treffer wäre keine
ausreichende SSM-Freigabe.

### MCU-Struktur

Alle folgenden Offsets beziehen sich auf die **vollständige MCU-Downloaddatei**,
nicht auf Flashadressen. Sie gelten nur für den oben genannten SHA-256-Hash.

| Dateioffset / Bereich | Tatsächlicher Befund |
| --- | --- |
| `0x00000` | Big-Endian-Längenfeld `0x24000`; mit `0x800` Vorspann exakt Dateilänge `0x24800` |
| `0x00012` | ASCII-Paketfeld `0108`; dieses Feld ist nicht die Katalogversion `0007` |
| `0x00022` | Modellkennung `000700010001` |
| `0x00800` | Brightway-Marker `DEPRD5C` |
| `0x01000` | Erster ARM-Vektortabellenkandidat: Stack `0x20004e40`, Resetvektor `0x0800315d` |
| `0x19800` | Beginn des eingebetteten ES32-Headers |
| `0x19810` | ASCII-Kennung `SZMC-ES-ZM-0283M` |
| `0x19830` | ES32-CRC `3426` |
| `0x19880` | Zweiter Vektortabellenkandidat: Stack `0x20001ba8`, Resetvektor `0x000000d5`; Beginn des ES32-Codebereichs |
| `0x19880` bis exklusiv `0x24710` | `0xae90` Bytes ES32-Inhalt entsprechend dem inneren Längenfeld |
| `0x24710` bis EOF | 240 aufeinanderfolgende `0xff`-Bytes |

Das Paket enthält zwei ausführbare ARM-Bereiche. Ihre vollständige
Boot-/Prozessorzuordnung ist offen. Dass der Modus-/Speed-Code im zweiten
Bereich liegt, ist durch die existierenden ES32-Patches und Disassemblierung
belegt. Eine konkrete Flashbasis für eigene Einsprünge wurde nicht freigegeben.

**CRC-Besonderheit:** `CorePatcher._compute_checksum()` prüft im Bestand nur
`size <= len(data)`, nicht `offset + size <= len(data)`. Beim Mi5Pro-Paket liest
der vorhandene Ablauf dadurch ein überlanges Slice ab `0x19800`, das Python
am EOF abschneidet. Am Original stimmt dessen CRC `7487` mit dem Paketfeld
bei `0x0a` überein. Die CRC über den gesamten angekündigten BW-Nutzbereich
ab `0x800` wäre dagegen `7379` und passt nicht zu diesem Feld.

Der neue Audit bildet den beobachteten Bereich explizit als
`[0x19800, 0x24800)` mit Länge `0xb000` ab. Die innere CRC wird über
`[0x19880, 0x24710)` berechnet. Beide CRCs stimmen beim Original. Der bestehende
Checksum-Patch erzeugt beim unveränderten Original identische Bytes. Der
erste Codebereich wird von diesen beiden CRCs nicht vollständig abgedeckt;
die zusätzliche SHA-256-Prüfung umfasst deshalb immer die gesamte Datei.
Das beobachtete Layout wird nicht als universelle BW-Spezifikation ausgegeben.

### Fahrmodi und Geschwindigkeitsbegrenzung

Belegte Fundstellen im zweiten ARM-Bereich:

| Dateioffset | Befund / begrenzte Interpretation |
| --- | --- |
| `0x1d0c8` | Literalpool bei `0x1d2f4` enthält `0x20000229` |
| `0x1d0d6` | Lesen dieses Zustandsbytes; Vergleiche mit `0x0b`, `2`, `3` folgen |
| `0x1d136` | Pfad `0x0b` setzt den Wert `125`, konsistent mit ca. 6 km/h bei bestehendem Faktor 20,9 |
| `0x1d13a` | Pfad `2` lädt über `0x20000324`; Bezugspunkt des bisherigen Drive-Patches |
| `0x1d140` | Pfad `3` lädt über `0x20000326`; Bezugspunkt des bisherigen Sport-Patches |
| `0x1d0e8` | Vergleich/Begrenzung nach Auswahl des modusabhängigen Wertes |
| `0x203b2` | Lesen eines Eingabebytes bei `[r0 + 3]` |
| `0x203ca` | Dessen unteres Nibble wird über Literal bei `0x20488` nach `0x20000229` geschrieben |

Damit sind ein Moduszustand und dessen Zusammenhang mit einer Eingabestruktur
statisch belegt. Das obere Nibble desselben Eingabebytes wird separat nach
`0x20000228` geschrieben und auf `1..3` begrenzt. Seine genaue Bedeutung
wurde nicht bestätigt und wird ausdrücklich nicht verändert.

Die vorhandenen Methoden `speed_limit_sport()` und `speed_limit_drive()`
ersetzen zusätzlich den zehn Byte langen Bereich bei `0x1d0e8` durch NOPs,
sofern das Pattern vorhanden ist. Das ist eine zusätzliche Begrenzungsprüfung.
Ihre vollständige Bedeutung und Sicherheitswirkung sind nicht geklärt. Die
Methoden werden deshalb **nicht** als SSM-Bausteine aufgerufen. `sls=30` allein
erzeugt weder einen vierten Zustand noch eine geheime Aktivierung.

### Tasten, Display und Kommunikation: aktualisierter Befund

Die [Fortsetzung](FORTSETZUNG.md) mit [maschinellen Nachweisen](BEFUNDE.json)
ersetzt den früheren offenen Stand dieses Abschnitts:

- Das APP ab BLE-Containeroffset `0xa000` ist LZMA-komprimiert. Zwölf Blöcke
  ergeben 181612 Bytes, drei interne SHA-256-Prüfungen stimmen. Hohe Entropie
  war kein Verschlüsselungsbeweis. Ein Teil des ROM-Patch-Images bleibt ungeklärt.
- Der Tastenpfad ist vom nominalen 10-ms-Timer über IO-Ereignis `0x1f` und
  APP+`0x82d4` bis zu den Automaten APP+`0x8260`/`0x81ce` und GPIO-Bit 29
  lokalisiert. Die Originalausführung bestätigt zwei frühzeitige Doppelklickereignisse
  in der geprüften Fünferfolge; statisch ist ein eigener OEM-Fünfer-/Resetpfad belegt.
- Die Anzeige-Bitmap `0x208660` ist vom skalaren Fahrmodus getrennt. Die Bits
  `1`, `2`, `4` und ihre Kombination `7` passieren originale Kopier- und
  Aggregationsroutinen bis zum Datenbyte für Adresskommando `0xc8`.
  Elektrische Segmentzuordnung und unbeeinträchtigte Warnanzeigen sind offen.
- Der BLE-Builder APP+`0x3940` erzeugt einen 12-Byte-Modusframe; der originale
  MCU-Feldkonsument bei Dateioffset `0x203b2` übernimmt daraus den Modus.
  Neun Kombinationen wurden über beide Originale geprüft. Das ist kein
  vollständiger UART-/RTOS-/Hardwaretest und noch kein SSM-Kommunikationsvertrag.
- Fünf vollständige Thumb-Instruktionen sind als semantische Hook-Kandidaten
  belegt: APP+`0x8264`, `0x82fc`, `0x8550`, `0x611c`, `0xc76c`. Sie sind **nicht zur
  Injektion freigegeben**. APP-Offsets sind keine direkten OTA-Dateioffsets.

Der aktuelle Befund erlaubt weiterhin **keinen belastbaren SSM-Firmware-Patch**.
Freier Flash-/RAM-Platz, vollständige Kontextverträge, sichere Geschwindigkeits-
und Fehlerübergänge sowie unveränderte Update-/Vertrauensanforderungen sind
noch nachzuweisen. Die 240 MCU-Paddingbytes sind kein freigegebener Codebereich.
Es wurden keine Sprünge oder geratenen Befehle injiziert.

## B. Implementierung

### Dateien und Schnittstellen

| Datei | Änderung |
| --- | --- |
| `bwpatcher/ssm.py` | OEM-Ereignissimulation: `Timing`, `Inputs`, `ModeRequest`, `SuperSportSimulation`; kein neuer Roh-Tastenparser |
| `bwpatcher/ssm_firmware.py` | Schreibgeschützter Audit, strikte Originalidentifikation, begrenzte CRC-Bereiche und reproduzierbare Disassemblierung |
| `bwpatcher/mi5pro_research.py` | Begrenzte Bee2-/LZMA-Analyse, Hashes, Codefenster und nicht freigegebene Hook-Kandidaten |
| `bwpatcher/mi5pro_emulator.py` | Kontrollierte Ausführung ausgewählter Originalroutinen mit emulierter Peripherie |
| `tests/test_mi5pro_research.py` | Neue Container-, Originalcode-, Anzeige- und BLE-/MCU-Feldprüfungen |
| `bwpatcher/ssm_demo.py` | Deterministische Offline-Demo einschliesslich Fahrt, vorgemerkter Deaktivierung und Neustart |
| `bwpatcher/utils.py` | SSM-Anforderungen vor erster Patchaktion abbrechen, auch gemischt mit vorhandenen Patches |
| `bwpatcher/__main__.py` | SSM-Fehler beendet CLI mit Code 1, ohne Ausgabedatei anzulegen/zu überschreiben; Hilfe ergänzt |
| `app.py` | Mi5Pro-Statusanzeige und standardmässig deaktivierte, gesperrte SSM-Checkbox |
| `tests/test_ssm.py` | OEM-Ereignis-, Modusquittungs-, Zustands-, Display- und Grenzfalltests |
| `tests/test_ssm_firmware.py` | Synthetische Struktur-/Exporttests und optionale Original-Regressionsprüfungen |
| `tests/test_ssm_ui.py` | Streamlit-Prüfungen und Demoablauf |
| `pyproject.toml` | pytest-Importpfad und optionale Forschungsgruppe mit Unicorn ergänzt |
| `.gitignore` | Python-Tests versionierbar gemacht; proprietäre Fixture-Verzeichnisse weiterhin ausgeschlossen |
| `README.md`, `docs/supersport/` | Status, Benutzung und Analyse dokumentiert |

Die bestehenden Mi5Pro-Patchmethoden, Stromparameter und Checksum-Algorithmen
wurden nicht umgeschrieben. Das Modell liegt ausserhalb des dynamisch erfassten
Modulverzeichnisses und wird nicht versehentlich als Scooter-Modell angeboten.

### Drei getrennte OEM-Doppelklicks

Die [aktuelle Ereignisspezifikation](DOPPELKLICK.md) ersetzt die frühere
Fünffachklick- und Rohpegel-Auswertung vollständig. Die Originalausführung
zeigt bei schnellen sechs Tastendrücken `2,2,5,2`, bei ausreichend getrennten
Paaren dagegen ausschliesslich `2,2,2`. Das OEM-Fünferereignis wird erhalten
und unterbricht SSM-Folgen. Es wird kein zweiter Roh-Tastenparser implementiert.

Die ersten beiden und der dritte normale Doppelklick dürfen die ursprüngliche
Modusaktion ausführen. Im Originalverteiler wurde damit der volle Zyklus
`Sport -> Fussgänger -> Drive -> Sport` geprüft. Nach jeder Aktion verlangt
`ModeRequest` ein passendes Abschlussticket und einen tatsächlichen Istmodus.
Nur die bestätigte dritte Aktion im Sportmodus kann aktivieren; ein bereits
zuvor angezeigtes Sport genügt nicht. Die aktuellen Grenzen sind 600–1600 ms
zwischen Doppelereignissen, 4000 ms Gesamtfenster, 500 ms Abschlussfrist und
mindestens 500 ms bestätigter Stillstand. Das sind Entwurfswerte, keine
Hardwaremessungen. Normale OEM-Aktionen werden nicht bis zum dritten Ereignis
zurückgehalten.

Aktivierung bleibt standardmässig deaktiviert. Bei eingeschalteter Simulation
müssen während der Folge Betrieb, bekannte gültige Telemetrie, Geschwindigkeit
exakt null, losgelassenes Gas, Fehlerfreiheit und entsperrter Zustand vorliegen.
Reservierte OEM-Kontexte müssen ausdrücklich ausgeschlossen sein. Andere
Tastenereignisse, unbekannte Werte, verlorene Freigaben, Timeout, fremde Tickets
und konkurrierende Dashboardereignisse verwerfen die Aktivierungsfolge.
Single-/Long-/Fünfer- und übrige OEM-Ereignisse werden unverändert delegiert.

Die zusätzlichen Kontext-/Quittungsfelder sind ein Vertrag für einen späteren
Adapter. Der vollständige reale Reset-, Tastenbeginn-, Scheduler- und
Motorcontroller-Rückmeldepfad ist damit nicht implementiert. Die Demo kennzeichnet
simulierte Quittungen, die erweiterten Originaltests nutzen ausgeführte
Original-Moduswechsel, BLE-Framebuilder und MCU-Feldkonsument. Beide bleiben
Offline-Prüfungen ohne angeschlossenen Scooter.

### Zustand, Rückkehr und Anzeige

```mermaid
stateDiagram-v2
    [*] --> Normal
    Normal --> SuperSport: 3 OEM-Doppelklicks, dritter Abschluss Sport, Stillstand
    SuperSport --> Normal: 1 Doppelklick im bestätigten Stillstand
    SuperSport --> RueckkehrVorgemerkt: Doppelklick während Fahrt oder Sicherheitsereignis
    RueckkehrVorgemerkt --> Normal: Bestätigter Stillstand
    SuperSport --> Normal: Ausschalten oder reset
    RueckkehrVorgemerkt --> Normal: Ausschalten oder reset
```

`speed_override_kmh` ist im Normalzustand `None`, im aktiven bzw. vorgemerkten
Zustand `30`. `None` delegiert an die Originalbegrenzung; die vorhandenen
Schweizer 20-km/h-Grenzen werden damit weder ausgelesen noch nachprogrammiert.
Die Simulation kann deren Vorhandensein am Gerät nicht nachweisen.

Die Rückkehr während der Fahrt wird vorgemerkt. Solange der Stillstand nicht
bestätigt ist, wird keine neue 20-km/h-Anforderung und kein Bremsbefehl erzeugt.
Fehler oder Telemetrieausfall verriegeln ebenfalls diese Rückkehrabsicht.
**Originale Fehlerabschaltung und Bremsfunktionen müssen jederzeit Vorrang
haben.** Ein vorhandener 30-km/h-Modellwert ist keine Erlaubnis, eine
Originalfehlerreaktion zu überstimmen. Dies muss beim späteren Port ausdrücklich
nachgewiesen werden. Nach `reset()` oder beobachtetem Ausschalten ist SSM aus;
es gibt keinerlei persistierten Aktivierungszustand. Sollte der tatsächliche
Modus unerwartet nicht Sport sein, bleibt die Rückkehr bis zum bestätigten
Sportzustand vorgemerkt; `RESTORE_SPORT` ist nur eine logische Adapteranforderung.

`display(frame)` kopiert nur den abstrakten Schlüssel `mode_icons`. Im normalen
Betrieb enthält er das aktuelle Modussymbol, während SSM und vorgemerkter
Rückkehr alle drei. Wiederholte Aufrufe ändern die Symbolmenge nicht; es gibt
keinen Blinktimer. Geschwindigkeit, Batterie, Licht, Bluetooth, Fehler,
Warnungen und unbekannte Felder bleiben unverändert. Das ist eine logische
Projektion für die Simulation, kein Dashboardpaket und keine elektrische
Segmentsteuerung. Der spätere Port braucht ausserdem eine Bestätigung des
tatsächlichen Modus, bevor er eine erfolgreiche Umschaltung anzeigen darf.

### Ausführen

```bash
# Nach Installation der Projekt- und Testabhängigkeiten
python -m bwpatcher.ssm_demo

# Nur Lesen, keine Firmwareausgabe
python -m bwpatcher.ssm_firmware --mcu /lokal/mcu_0007.bin --ble /lokal/ble_2.7.0_0015.bin

# Fundstellen inkl. aufgelöster PC-relativer Literalpools
python -m bwpatcher.ssm_firmware --mcu /lokal/mcu_0007.bin --disassemble

# Ohne Originale: nur öffentliche, synthetische Tests
python -m pytest tests -q

# Mit lokal vorhandenen, exakt passenden Originalen
MI5PRO_FIRMWARE_DIR=/lokal/originale python -m pytest tests -q
```

Erwartete Dateinamen im lokalen Originalverzeichnis sind `mcu_0007.bin` und
`ble_2.7.0_0015.bin`. Der Audit-Exitcode 0 bedeutet identifizierte untersuchte
Originale, **keine Patchfreigabe**. `ssm_patch_available` bleibt immer `false`.
Weder `--experimental` noch der Web-Queryparameter entsperren SSM. Ein Versuch
wie `ssm` oder `sls=30,ssm,chk` wird vollständig vor der Patchausführung abgewiesen.

## C. Testergebnisse

Die vollständige aktuelle Suite wurde mit beiden Originaldateien ausgeführt:

| Testumfang | Ergebnis |
| --- | --- |
| Alle Tests, lokale Originale und optionale Forschungsabhängigkeiten | **219 bestanden, 0 fehlgeschlagen, 0 übersprungen** |
| Alle Tests ohne proprietäre Originaldateien | **172 bestanden, 47 Originalfälle übersprungen** |
| Hardwaretests | 0 |

Enthalten sind 107 Ereignis-/Zustandsfälle, 65 Container-/Originalcodefälle,
44 Audit-/Exportsperrfälle und drei GUI-/Demofälle. Python 3.12, Unicorn 2.1.4,
Capstone 4.0.2, pytest 8 und Streamlit AppTest. Die bekannte Capstone-
`pkg_resources`-Abkündigungswarnung bleibt; Setuptools ist 80.9.0.

Geprüft sind normale Einzel-/Doppel-/Langdruckübergaben, weitergereichte OEM-
Fünfer-/Resetereignisse, Mindest-/Maximal-/Gesamtfristen, dritte Modusquittung,
fehlerhafte/veraltete Tickets, verlorene Freigaben, ursprüngliche Moduswechsel,
Deaktivierung, vorgemerkte Rückkehr, Neustart, Displayfelder und 6000
Zufallssamples mit Bewegung ohne SSM-Aktivierung. Die Originalprüfungen umfassen
LZMA-/Hash-/Grenzfälle, tatsächliche Klassifikator- und Verteilerfunktionen,
Licht-GPIO im emulierten Speicher, ursprüngliches Modussperrbyte sowie
BLE-/MCU-Feldvergleiche. Einzelheiten stehen in [DOPPELKLICK.md](DOPPELKLICK.md).

Die sechs bisherigen Originaltests inklusive rein im RAM geprüfter alter
SLS-/SLD-Patches und Checksum-Behandlung sind im Gesamtlauf enthalten. Sie
bedeuten weiterhin keine Sicherheitsfreigabe dieser alten Speed-Patches.
CLI-/GUI- und Mischpatchtests bestätigen die unveränderte SSM-Exportsperre.

Die früheren Ergebnisse 114/108 und der gezielte Fortsetzungslauf mit 55 Fällen
sind historische Nachweise vorheriger Stände. Die dort erhobenen Python-
Abdeckungswerte gelten nicht für die aktuelle Ereignissimulation. Es wurden
keine integrierten SSM-Einsprünge, keine elektrische Segmentanzeige, keine
Fahrdynamik und keine realen Schutzreaktionen geprüft. Entwicklungsstufe 4
„Firmware-Patch offline validiert“ bleibt unerreicht.

## D. Sicherheits- und Kompatibilitätsprüfung

Es existiert kein neuer Pfad, der Firmwarebytes für SSM verändert. Die
Originaldateien bleiben unverändert, SSM-Exportanforderungen brechen ab und
die Simulation besitzt keine Schnittstelle zu seriellen Geräten oder BLE.
Entsprechend wurden für SSM weder Strom-/Leistungs-/Beschleunigungswerte
noch Temperatur-, Batterie-, Unter-/Überspannungs-, Motor-, Rekuperations-,
Brems-, Fehler- oder Notabschaltparameter geändert. Es wurde keine
Integritäts-/Authentifizierungsprüfung entfernt.

Das beweist die Unverändertheit des aktuellen Forschungsstands, nicht die
Sicherheit einer zukünftigen Implementierung. Statische Fundstellen und
Modelltests können weder tatsächliche Strom-/Temperaturgrenzen noch
Bremswirkung unter Last beweisen. Ebenso sind die Erreichbarkeit von 30 km/h
bei Originalleistung und die Dauerhaltbarkeit ungeprüft. Die Implementierung
erhöht keine Leistung, um das Ziel zu erzwingen.

Xiaomi Home, Rekuperationsstufen niedrig/mittel/hoch, Kilometerstand,
Akkustand, Sperre, Bluetooth und Geräteinformationen wurden nicht auf echter
Hardware getestet. Xiaomi beschreibt die drei Rekuperationsstufen in seiner
FAQ; deren konkrete Speicher-/Protokollfelder wurden hier nicht freigegeben.
Der Konflikt mit den Original-Resetkombinationen ist vor einem Firmwareport
aufzulösen. Diese Modifikation erhält durch diesen Bericht keine Zulassung
für öffentliche Strassen in der Schweiz.

## E. Noch benötigte Nachweise und nächste Schritte

Die beiden Originaldateien sind vorhanden; eine erneute Bereitstellung ist
nicht erforderlich. Die [detaillierte Trennung der Hindernisse](FORTSETZUNG.md#8-werkzeuge-prüfungen-und-verbleibende-arbeit)
ist massgebend für die Fortsetzung.

Noch softwareseitig offen:

1. Vollständige Referenz-/Kontrollflussanalyse, Flash-/RAM-Reservierung,
   Initialisierung, Live-Register und Kontextverträge der Hook-Kandidaten.
2. Integration eines Zählers vorhandener OEM-Doppelereignisse und bestätigter
   Original-Modusabschlüsse bei Erhalt von Langdruck, Reset und sonstigen
   Originalkombinationen. Ein neuer Rohklassifikator ist nicht mehr nötig.
3. Vollständiger Kommunikationsvertrag für SSM zwischen BLE und MCU,
   einschliesslich Fehlern, Quittierung, Telemetriefrische und Neustart.
4. Normalwert aus Region/NVM erhalten und sichere Umschaltstelle ohne Entfernung
   der bestehenden Begrenzungsprüfung nachweisen. Originale Update- und
   Vertrauensprüfungen dürfen nicht umgangen werden.

Zwingend auf echter Hardware zu messen:

1. Tatsächliche Dashboard-/Controllerrevision, Tasterpegel, Prellen und
   Scheduler-/Ende-zu-Ende-Latenz unter konkurrierenden Ereignissen.
2. Physische UART-Leitungen, Pegel, Baudrate, Übertragungsfehler und Zeitverhalten.
3. Displaytreiber, Segmentzuordnung, dauerhaftes gemeinsames Leuchten der drei
   Piktogramme, Helligkeit/Strom und Vorrang von Warn-/Fehleranzeigen.
4. Laufzeit unter Last, reale Stillstands-/Geschwindigkeitswerte, sichere
   Übergänge, Strom-/Temperatur-/Brems-/Schutzreaktionen und Xiaomi-Home-Verhalten.

Ein Hardwaretestaufbau braucht eine getrennte ausdrückliche Autorisierung.
Zuerst kommen passive Tasten-/UART-/Displaymessungen und Prüfungen ohne Antrieb;
ein Fahrtest allein ersetzt keine Schutzprüfung. Es wird nicht automatisch
geflasht. Die neuen Softwarebelege ersetzen keine dieser Messungen.

## F. Entwicklungsstatus und Quellen

| Stufe | Erreicht? |
| --- | --- |
| 1. Theoretisches Konzept | Ja |
| 2. Quellcode implementiert | Ja, Referenzsimulation und Forschungswerkzeuge |
| 3. Simulation erfolgreich | **Ja, aktueller Gesamtstand** |
| 4. Firmware-Patch offline validiert | Nein; die Prüfung bestehender Patches ist kein SSM-Patch |
| 5. Auf echter Hardware geprüft | Nein |

Änderungsziel ist ausschliesslich der Fork
[Domangy/bw-patcher](https://github.com/Domangy/bw-patcher), Branch
`codex/mi5pro-ssm-research`. Am Originalrepository wurden keine Änderungen
vorgenommen und kein Pull Request eröffnet. Der Forschungsstand liegt als
[Draft-PR #1](https://github.com/Domangy/bw-patcher/pull/1) gegen `master` im Fork vor.

Die zusätzliche SDK-, Firmware-, Protokoll- und Schaltplanrecherche ist mit
fixierten Quellständen in [FORTSETZUNG.md](FORTSETZUNG.md#7-öffentliche-recherche-und-quellenbewertung)
dokumentiert. Quellen für ursprüngliche Zuordnung und Originalbedienung:

- [Firmwarekatalog, fixierter Commit](https://github.com/argusblack/mi-fw-info/blob/ae9260764c863aede29bba8053c1986645e1e07f/mi.json)
- [Katalogoberfläche: Benennung des BLE-Downloads](https://github.com/argusblack/mi-fw-info/blob/ae9260764c863aede29bba8053c1986645e1e07f/static/app.js)
- [Mi5Pro-Patcher der untersuchten Fork-Codebasis](https://github.com/Domangy/bw-patcher/blob/95a8f339787a1fb6486554d61b573b8e2b688c53/bwpatcher/modules/mi5pro.py)
- [ES32-Checksum-Pfad derselben Codebasis](https://github.com/Domangy/bw-patcher/blob/95a8f339787a1fb6486554d61b573b8e2b688c53/bwpatcher/core_es32.py)
- [Xiaomi-FAQ: Originalkombinationen und Rekuperation](https://www.mi.com/uk/support/faq/details/KA-504123/)

Firmwarebinärdateien und proprietäre Dumps sind nicht Bestandteil dieses
Berichts, der Tests oder des Pull Requests.
