# Mi5Pro: Nachweise aus der Originalfirmware

Stand: 14. Oktober 2026. Fortsetzung von Draft-PR #1 auf Basis von
`b2965be621fa5e8fe32a1748313fbb37158373e7`.

Die ursprünglichen 55 Testergebnisse unten dokumentieren den Stand `6062bd2`.
Die aktuelle Aktivierung verwendet drei getrennte OEM-Doppelklicks; neue
Verteiler-/Lichtnachweise und der vollständige Testlauf stehen in
[DOPPELKLICK.md](DOPPELKLICK.md). Container- und Adressbefunde bleiben gültig. Die aktuelle Fortsetzung vom
15. Oktober zu Speicherbelegung, Hook-Kontexten, originaler Begrenzungsauswahl,
Status-Rückkanal und unabhängiger Absichtsfreigabe steht in
[INTEGRATION.md](INTEGRATION.md); dort stehen auch der aktuelle Gesamttest und
die konkret notwendigen Hardwaremessungen.

**Neue Nachweise:** Das komprimierte BLE-APP ist vollständig lesbar. Der
ursprüngliche GPIO-/Tastenpfad und die getrennte Display-Bitmap sind lokalisiert.
Ausgewählte Originalroutinen wurden mit Unicorn ausgeführt; der originale
BLE-Modusframe wurde an den originalen MCU-Feldkonsumenten übergeben.
Das geht über die bisherige Python-Referenzsimulation hinaus. Es ist weiterhin
kein integrierter SSM-Patch und kein Hardwaretest. Die Exportsperre bleibt bestehen.

## 1. Identität und Beweisgrenzen

Untersucht wurden ausschliesslich die bereits vorhandenen CDN-Originale:

| Datei | Bytes | SHA-256 |
| --- | ---: | --- |
| MCU `0007` | 149504 | `ddcd65400c4fbdb45cb4cdbec2e812026d7bc6cb755fd9dd0180800caed5f9b8` |
| BLE `2.7.0_0015` | 152552 | `061d34cac06fb31d93ff8f47650cd09d61fa46e7a883b35c23f35cabff1e6df7` |
| Intern entpacktes BLE-APP | 181612 | `95edba0d2d4a46405bfbb1a433b7ad4c1c72fc1787bc76eefe99a727c711bbae` |

Die Originale und das abgeleitete APP liegen ausserhalb des Repositories.
Die Analysewerkzeuge geben JSON aus, keine Firmwaredatei. Exakte Hashprüfungen
verhindern die Anwendung der dokumentierten Codeadressen auf andere Versionen.

Alle nachstehenden **APP-Offsets** beziehen sich auf das entpackte Image
einschliesslich seines 1024-Byte-Headers. Seine im Header gespeicherte Basis ist
`0x0080e000`; ausführbarer APP-Code beginnt bei `0x0080e400`.
Eine Laufzeitadresse ist `0x0080e000 + APP-Offset`. MCU-Dateioffsets beziehen sich
weiterhin auf die gesamte MCU-Datei. Beide sind von BLE-Containeroffsets zu trennen.

Die Emulation startet einzelne Funktionen mit gezielt initialisiertem RAM,
GPIO-Registern und Stack. Sie startet weder den kompletten Bootvorgang noch
einen RTOS-/Funkstack. Unbekannte externe Aufrufe, unzulässige Schreibzugriffe,
ungültige Rückkehr und erschöpfte Instruktionsbudgets führen zum Abbruch.
Der APP-Bereich ist nur lesbar/ausführbar. Stackausgleich und Erhalt von
R4–R11 mit verschiedenen, von null verschiedenen Ausgangswerten werden bei
erfolgreichen Funktionsaufrufen geprüft. Das beweist keinen Vertrag für einen
noch nicht geschriebenen Hook und keine maximale Laufzeit auf dem Prozessor.

Maschinenlesbare Container-, Hook- und Ausführungsergebnisse:
[BEFUNDE.json](BEFUNDE.json). Reproduzierbare Prüfungen:
[`test_mi5pro_research.py`](../../tests/test_mi5pro_research.py).

## 2. BLE-Dateiformat: Kompression nachgewiesen

Der früher unbekannte Bereich ab `0xa000` ist in dieser Datei ein komprimiertes
APP. Seine hohe Entropie war kein Verschlüsselungsnachweis. Es wurden keine
Schlüssel beschafft oder Sicherheitsprüfungen deaktiviert.

| Containerbereich | Nachweis |
| --- | --- |
| `0x0000..0x9ff4` exklusiv | ROM-Patch-Image `0x2792`, Header 1024 Bytes, Nutzlänge `0x9bf4` |
| `0x9ff4..0xa000` | 12 Bytes `ff`, Ausrichtung auf 16 Bytes |
| `0xa000..0xa060` | Kompakt-Header, 96 Bytes, Image-ID `0x2793`, Flags `0x2181`, Typ 1 |
| `0xa060..0x253e8` | Komprimierter Nutzbereich, Länge `0x1b388`, Algorithmusfeld 1 |

Der beobachtete ältere Bee2-Kontrollheader hat das Layout `<BBHHHI`:
IC-Typ, Secure-Version, Flags, Image-ID, CRC16-Feld und Nutzlänge. Bei den
neuen Realtek-SDKs ist die Reihenfolge dieses Kontrollheaders anders; sie darf
nicht unverändert übernommen werden. Der gemeinsame Kompakt-Headeraufbau
enthält UUID bei +12, Version bei +28, Algorithmus bei +32 und SHA-256 bei +36.
Alle drei Image-UUIDs stimmen überein.

Die komprimierten Records bestehen aus `<IHH>` und einem vollständigen
LZMA-alone-Stream: Markierung, entpackte Länge und gepackte Länge. Markierung
`0xfffdff00` bedeutet hier weiterer Block, `0xffffff00` letzter Block.
Elf Blöcke liefern je 16384 Bytes, der letzte 1388 Bytes. Drei abschliessende
`ff`-Bytes stellen die Vierbyte-Ausrichtung her. Die Streams verwenden
LZMA-Properties `5d` und ein 4096-Byte-Wörterbuch. Längen, Streamenden und
Padding werden einzeln geprüft. Das Ergebnis hat Headerflags `0x0101`,
Image-ID `0x2793` und Nutzlänge `0x2c16c`.

Drei unabhängig nachgerechnete, intern gespeicherte SHA-256-Werte stimmen:

| Bereich | SHA-256 |
| --- | --- |
| ROM-Patch-Image, Header-Prüfbereiche | `e46b3499cd6e90eb3c8513b8658634e2b6b12342a913b4fed962cc14b9176f3d` |
| Komprimierter APP-Nutzbereich | `fc2469fe23c91bfe3b5a87bafca6741ac1bc9f11f396bd4f820ba031ba18fdd6` |
| Entpacktes APP, Header-Prüfbereiche | `cd7638f9e2bc797a57e20325f5a42606583111e0fe6d2120999333a022740cfe` |

Bei den 1024-Byte-Headern wird relativ zum jeweiligen Image die Verkettung
`[12,0x174) + [0x194,0x2f0) + [0x3f0,Imageende)` gehasht; der gespeicherte Wert
liegt bei `[0x174,0x194)`. Beim Kompakt-Header wird nur sein Nutzbereich gehasht.
Diese Konsistenzprüfungen sind **keine Herstellersignaturprüfung** und keine
Aussage darüber, welche geänderten Images ein reales Gerät akzeptieren würde.

Nicht das gesamte ROM-Patch-Image ist damit als Klartext erklärt: Seine Flags
enthalten ein Verschlüsselungsbit. Es beschreibt ein geladenes Teilstück mit
Image-Basis `0x01803000`, Ladebasis `0x01805fc8`, Ausführungsbasis `0x00203800`
und Länge `0x2e00`. Der zugehörige Dateibereich `[0x2fc8,0x5dc8)` bleibt ungeklärt.
Für die hier belegten APP-Funktionen war dessen Dekodierung nicht erforderlich.

## 3. Ursprüngliche Tastenverarbeitung

Die statisch nachvollzogene Aufrufkette lautet:

```text
Timerregistrierung APP+0x19712, nominal 10 ms
  -> Callback APP+0x9e34 -> IO-Ereignis 0x1f
  -> registrierter IO-Handler APP+0x9e18
  -> Tastenaktionsverteiler APP+0x82d4, Argument 1
  -> Mehrfachklickklassifikator APP+0x8260
  -> Phasenautomat APP+0x81ce
  -> GPIO-Leser APP+0x8ac6, MMIO 0x40001050
```

Die Timerregistrierung enthält zusätzlich den Originaltext
`start set button scan %d ms`; bei APP+`0x19758` wird das Intervall 10 gesetzt.
Die Handlerregistrierung bei APP+`0xc05c` verweist auf APP+`0x9e18` mit Thumb-Bit.
Der Pin-ID-Mapper APP+`0xd9e` bildet ID `0x21` auf GPIO-Bit 29 ab. Die wirkliche
Platinenbeschriftung, Tasterbeschaltung und elektrische Polarität sind ungemessen.

Der Phasenautomat benutzt Zustand bei `0x208624`, unter anderem das Phasenbyte
bei +`0x13` und Zähler bei +`0x1c`, +`0x1e`, +`0x20`. Die Vergleiche 250 und 450
führen im kontrollierten Dauerdruck zu Ereignis 3 nach 252 Aufrufen und Ereignis 6
nach 702 Aufrufen; Loslassen liefert Ereignis 7. Der Mehrfachklickautomat
verwendet ein Ruhefenster von 50 Aufrufen. Die Zahlen sind Aufrufzahlen;
`Aufrufe × 10 ms` ist eine nominale Einordnung, keine Zeitmessung am Scooter.

Unveränderte Originalroutinen wurden mit GPIO-Bit 29 ausgeführt: je Klick acht
Aufrufe mit Pegel 1 und acht mit Pegel 0, anschliessend 60 mit Pegel 0. Der
GPIO-Leser und Mapper liefen tatsächlich; sie wurden nicht durch einen
Python-Ereignisgenerator ersetzt. Ergebnis des Mehrfachklickklassifikators:

| Eingabe | Ereignisse `(Aufruf, Code)` |
| --- | --- |
| 1 Klick | `(59,1)` |
| 2 Klicks | `(25,2)` |
| 5 Klicks | `(25,2), (57,2), (73,5), (123,1)` |

Damit ist der Präfixkonflikt im Originalcode bewiesen: Eine Fünferfolge liefert
bereits zweimal Ereignis 2, bevor Ereignis 5 erscheint. Der Verteiler behandelt
Ereignis 2 ab APP+`0x8530` und kann bei erfüllten Originalbedingungen über
APP+`0x8550` die Moduswechselroutine APP+`0x80aa` aufrufen. Die Moduswechsel
selbst wurden in diesem Test nicht ausgeführt; der Klassifikator wurde isoliert.

Der Fünferpfad ab APP+`0x85b6` enthält bereits Originalbedingungen und einen
Resetpfad. Er ist keine unbenutzte SSM-Geste. Ein zukünftiger Adapter muss die
Originalaktionen einschliesslich Gas-/Resetkombinationen erhalten. Ein Hook
erst nach dem bestehenden Moduswechsel kann den Präfixkonflikt nicht lösen.

## 4. Display: drei unabhängige Softwarebits

Die Firmware trennt zwei Zustände:

| Bedeutung | Speicher / Werte |
| --- | --- |
| Tatsächlicher Fahrmodus als skalarer Code | `0x20826d`: Walk `11`, Drive `2`, Sport `3` |
| Nur Anzeige-Bitmap | `0x208660`: Walk `1`, Drive `2`, Sport `4` |
| Anzeige-Staging | `0x2088b0`, 21 Slots zu 8 Bytes; Modus ist Slot 12 bei +`0x60` |

Die Zuordnung stammt aus den Originalzweigen der Moduswechselroutine
APP+`0x80aa`: `11 -> 2 -> 3 -> 11`. Sie schreibt die zugehörigen Bitmapwerte
getrennt vom skalaren Fahrmodus. Bei APP+`0x611c` kopiert die Routine
APP+`0x60f4` die Bitmap byteweise nach Slot 12. Die Ausführung dieser Routine
bestätigt die unveränderte Übernahme von `1`, `2`, `4` und `7`, ohne den
Sportmodus bei `0x20826d` zu ändern.

Der Renderer APP+`0xc6b2` bearbeitet Slotstatus und Blinkzähler, aggregiert
21 logische Slots und gibt sieben Anzeigebytes aus. Byte 1 eines Slots ist
Status: 0 aus, 1 dauerhaft, 2 Blinkverarbeitung. APP+`0xc76c` liest Slot 12 und
verodert ihn in das spätere Byte für Adresskommando `0xc8`.

In der Emulation laufen Aggregation und Blinkverarbeitung unverändert.
Abgefangen werden die Ausgänge zum Byte-Schieber APP+`0xc44a`, zur
Kommandohilfe APP+`0xc4a6` und der abschliessende ROM-Pinkonfigurationsaufruf.
Bei ausschliesslich belegtem Modusslot mit Status 1 ergeben sich:

| Slot-12-Bitmap | Datenbyte für `0xc8` | Übrige sechs Datenbytes |
| ---: | ---: | --- |
| 1 | 1 | jeweils 0 |
| 2 | 2 | jeweils 0 |
| 4 | 4 | jeweils 0 |
| 7 | 7 | jeweils 0 |

Mit weiteren gesetzten Slots bleiben beim Wechsel `1 -> 7` die anderen sechs
Ausgabebytes, die übrigen Bits des Modusbytes und der separat initialisierte
Fahrzeugzustand erhalten. Zehn weitere Rendereraufrufe erzeugen dieselben
Bytes. Das prüft diesen stationären Kontext; Warn-/Fehlerprioritäten in allen
Betriebszuständen sind damit nicht abgedeckt.

Statisch erkennbar sind acht Bits LSB zuerst im Schieber, GPIO-IDs `0x1a`
(Takt), `0x1b` (Daten), `0x26` (Strobe) und Kommandos `0x40`, `0xc0..0xcc`
in Zweierschritten sowie `0x8f` beziehungsweise `0x89` zur Helligkeitssteuerung.
Das ähnelt TM16xx-Protokollen, identifiziert aber keinen bestimmten Treiberchip.
GPIO-IDs sind keine Steckerpin-Nummern.

**Softwareseitig ist die unabhängige Ansteuerbarkeit der drei Bitmapbits bis
zur Byte-Ausgabeschnittstelle belegt.** Ob sie auf der vorhandenen Schweizer
Platinenrevision tatsächlich gleichzeitig die drei gewünschten Piktogramme
dauerhaft und ohne Nebenwirkungen beleuchten, erfordert eine elektrische und
optische Messung. Eine Modus-Bitmap `7` darf niemals als Motor-Fahrmodus
übertragen werden.

## 5. BLE-Kommunikation zum Motorcontroller

Der originale BLE-Builder APP+`0x3940` erzeugt in den geprüften Zuständen einen
12-Byte-Statusframe. APP+`0x3a52` packt oberes Nibble und Fahrmodus zusammen:

```text
51 10 07 [oberes Nibble << 4 | Fahrmodus] [6 weitere Statusbytes] SUM AE
SUM = Summe der ersten 10 Bytes modulo 256
```

Der UART-Schreiber APP+`0x9300` verwendet MMIO-Basis `0x40011000` und
Datenregister +`0x24`. Der Test fängt diesen Aufruf ab und liest dessen
fertigen Frame; er simuliert keine elektrische UART-Verbindung. In einem
gezielt freigegebenen, sonst nullinitialisierten Fahrzeugzustand mit oberem
Nibble 2 entstehen beispielsweise:

| Fahrmodus | Originalframe |
| --- | --- |
| Walk 11 | `5110072b00000000000093ae` |
| Drive 2 | `511007220000000000008aae` |
| Sport 3 | `511007230000000000008bae` |

Der Builder enthält zusätzliche Originalbedingungen, die Felder und Modus
überschreiben können. Die Beispiele sind keine universellen Solltelegramme.

Der nächste Prüfschritt führt das unveränderte MCU-Fragment an den vollständigen
Dateioffsets `[0x203b2,0x203d2)` aus, abgebildet entsprechend dem inneren
ES32-Codebeginn `0x19880`. Es übernimmt den Modus aus Byte 3 nach
`0x20000229` und das obere Nibble nach `0x20000228`, dort begrenzt auf `1..3`.
Alle neun Kombinationen aus drei normalen Modi und oberen Nibblewerten
`1..3` passieren diesen Vergleich zwischen beiden Originaldateien korrekt.
Die genaue Bedeutung des oberen Nibbles ist weiterhin nicht unabhängig belegt.

Das Fragment ist **kein vollständiger UART-Empfänger**. Framegrenzen und
Prüfsumme werden im Testwerkzeug vorgeprüft; IRQ, Empfangspuffer,
Resynchronisierung, physische Baudrate, Pegel, Steckerkontakte, Antwortzeiten
und alle Gegenrichtungsnachrichten sind damit nicht validiert. Angaben anderer
Projekte wie USART3/USART4 oder 19200 Baud werden nicht als eigene Messung
übernommen. In diesem Frame gibt es keine nachgewiesenen Roh-Tastenzeitstempel
und keinen bestätigten zusätzlichen SSM-Zustand oder freien Protokollbitplatz.

## 6. Einsprungstellen und technische Einschränkungen

Die folgenden Stellen sind semantisch zugeordnet und bestehen im exakten APP
jeweils aus einer vollständigen vier Byte langen Thumb-Instruktion. Das
Analysewerkzeug prüft auch Operanden, Sprungziel und zugehörigen komprimierten
Block. **Keine Stelle ist bereits für eine Codeinjektion freigegeben.**

| APP-Offset / Laufzeitadresse | Originalinstruktion / Zweck | Lokale Einschränkung |
| --- | --- | --- |
| `0x8264` / `0x00816264` | `BL` nach APP+`0x81ce`, vor dem Phasenautomaten | R0 liefert Phasenereignis; R4=0 und OEM-Zählerzustand bleiben erforderlich. Nur dieses Ereignis zu beobachten verhindert keine frühzeitigen Doppelklickaktionen. |
| `0x82fc` / `0x008162fc` | `BL` nach APP+`0x8260`, Klassifikator vor Aktionsverteiler | R0 ist das fertige Ereignis. Für die neue Variante den Originalklassifikator erhalten und andere OEM-Ereignisse zur Unterbrechung der Zählung beobachten; kein neuer Rohparser. |
| `0x8550` / `0x00816550` | `BL` nach APP+`0x80aa`, ursprünglicher Moduswechsel nach OEM-Prüfungen | Neue Doppelklick-Variante: Originalaktion erhalten, danach lokalen Istmodus lesen. SSM-Aktivierung braucht zusätzlich bestätigten Motorzustand; keine Injektionsfreigabe. |
| `0x611c` / `0x0081411c` | `STRB.W r0,[r4,#0x60]`, Bitmapkopie | R4 ist Stagingbasis; R5 bleibt live. Slotstatus und spätere Überschreibungen beachten. |
| `0xc76c` / `0x0081a76c` | `LDRB.W r0,[r4,#0x60]`, spätes Anzeige-Overlay | R0 geht in R5 ein; R1 und R4–R11 sind live. Das ist keine normale Funktionsgrenze; ein BL ohne Sicherung würde Live-Register und LR gefährden. |

Die Fortsetzungsadresse ist jeweils die Laufzeitadresse +4. Die drei
Tastenstellen liegen im komprimierten Block bei Containeroffset `0xf5c7`,
die Kopierstelle im Block `0xcbb5`, das späte Overlay im Block `0x1195a`.
Es gibt keinen direkten OTA-Byteoffset für eine entpackte Instruktion.
Vier Byte Platz und eine encodierbare Verzweigung beweisen weder freien
ausführbaren Speicher noch einen sicheren Hook.

Noch softwareseitig zu lösen sind vollständige eingehende Code-/Datenreferenzen,
Kontrollfluss und Registerlebensdauer, Flash-/RAM-Reservierung und Initialisierung,
die ursprünglichen Update-/Vertrauensanforderungen sowie ein bestätigter
SSM-Zustandsvertrag zwischen BLE und MCU. Der Schweizer Normalwert muss aus
dem wirklichen Gerätezustand erhalten bleiben. Eine neue 30-km/h-Umschaltstelle
ohne Entfernung der bestehenden Begrenzungsprüfung ist nicht nachgewiesen.
Die alten SLS-/SLD-Patches werden dafür weiterhin nicht verwendet.

## 7. Öffentliche Recherche und Quellenbewertung

Recherche nach Modellname, BLE-/MCU-Versionen, Bee2-Kompressionsheadern,
Dashboard, Schaltplänen und UART-/BLE-Protokollen am 14. Oktober 2026:

| Quelle | Verwendbarer Befund und Grenze |
| --- | --- |
| [Realtek RTL8752H SDK, Header, fixierter Commit](https://github.com/rtkconnectivity/rtl8752h_sdk/blob/6468ab3aac426a643e54f2bb1e0d99d5599aa4c1/inc/platform/patch_header_check.h) | Herstellerquelle für 96-Byte-Kompakt-Header und Image-Typ. Anderer IC-/Kontrollheader; kein Mi5Pro-Schaltplan. |
| [Realtek DFU-Prüfung, gleicher Commit](https://github.com/rtkconnectivity/rtl8752h_sdk/blob/6468ab3aac426a643e54f2bb1e0d99d5599aa4c1/src/platform/dfu_flash.c) | `dfu_check_compressed_image_sha256` erklärt den separaten Payload-Hash. Standarddekompression und passende Hashes bestätigen das Format an unserer Datei. |
| [RTL8762 SDK-Spiegel, Legacy-Header](https://github.com/GeFengthe/RTL8762/blob/f80ae6a2362d986a3d69c764ca1cda3ec39155c5/inc/platform/patch_header_check.h) | Ältere Kontrollheaderreihenfolge und Image-IDs; unabhängiger Spiegel, kein Nachweis des verbauten Siliziummodells. |
| [SCOOTER_5_PRO, BLE-Analyse](https://github.com/KuziaMother/SCOOTER_5_PRO/blob/3a3f5d9dfbb0ec1ca93042281134ecea0413397f/docs/BLE.md) und [MCU-Analyse](https://github.com/KuziaMother/SCOOTER_5_PRO/blob/3a3f5d9dfbb0ec1ca93042281134ecea0413397f/docs/MCU.md) | Nützliche Suchhinweise zu Realtek und gepackten Zuständen. Untersucht andere Dateien: dort BLE-MD5 `0d41b4df91f8d37b5f1355484e2b93c3`, 153890 Bytes. Eine dort angenommene APP-Verschlüsselung gilt nicht pauschal für unser LZMA-APP. Adressen und Hardwarebehauptungen wurden nicht ungeprüft übertragen. |
| [xiaomi-scooter-link, fixierter Commit](https://github.com/desperado0044/xiaomi-scooter-link/tree/8dedc6ef94e542a5e31a70463a9f4a0384492529) | Öffentlich dokumentierter Android-/MiOT-BLE-Zugang mit angegebenen Tests an 5 Pro/Max. App-Authentifizierung ist vom internen Motor-UART-Protokoll zu trennen. Kein Gerät kontaktiert und kein Authentifizierungspfad verändert. |
| [Navee ST3 Pro, Hardware-Dokumentation](https://github.com/pepperonas/navee-st3-pro/blob/7f346d38aea83b8e12bb44e31d8948f886eb1cc5/docs/HARDWARE.md) | Verwandtes Realtek-Umfeld, aber anderes Modell. Keine Übernahme von Stecker-/Segmentbelegung. |
| [FCC-Unterlagen 2AFZZ-MHBC50ZM](https://fccid.io/2AFZZMHBC50ZM) | Öffentliche interne Fotos gelistet; Schaltplan und Blockdiagramm nur als Metadaten, ohne öffentlich lesbaren Inhalt in dieser Quelle. Keine verifizierte Schaltung der vorhandenen Schweizer Revision gefunden. |
| [Xiaomi-Bedienungsanleitung](https://cdn.azams0.fds.api.mi-img.com/xiaomi-b2c-i18n-upload/User-Guide-Upload-mi.com/Personal_Care/60555-Xiaomi-Electric-Scooter5-Pro-UserGuide-GL.pdf) und [FAQ](https://www.mi.com/uk/support/faq/details/KA-504123/) | Originalbedienung und Resetkombinationen; keine technische Segment-/UART-Spezifikation. |

Fremde Hardwarefotos, ähnliche Modellnamen und SDKs ersetzen keinen Abgleich
mit der tatsächlichen Dashboard-/Controllerrevision. Ein geeigneter öffentlich
zugänglicher Schaltplan wurde in den geprüften Quellen nicht gefunden; das ist
keine Behauptung, dass weltweit keiner existiert. Fremde Flash-/Untersuchungstools
wurden nicht ausgeführt und kein SDK-Code in die Analysewerkzeuge kopiert.

## 8. Werkzeuge, Prüfungen und verbleibende Arbeit

Neu sind `bwpatcher.mi5pro_research` (begrenzter Parser und Codebelege) sowie
`bwpatcher.mi5pro_emulator` (isolierte Originalausführung). Der bestehende
schreibgeschützte Audit zeigt jetzt auch die BLE-Struktur. Der Exportpfad und
die SSM-Referenzzustandsmaschine wurden nicht verändert.

```bash
poetry install --with research

# Nur JSON-Berichte; keine Firmwareausgabe
python -m bwpatcher.mi5pro_research /lokal/originale/ble_2.7.0_0015.bin --evidence
python -m bwpatcher.mi5pro_emulator --ble /lokal/originale/ble_2.7.0_0015.bin --mcu /lokal/originale/mcu_0007.bin

# Neue Nachweise und die vom Audit betroffenen bisherigen Fälle
MI5PRO_FIRMWARE_DIR=/lokal/originale python -m pytest tests/test_mi5pro_research.py tests/test_ssm_firmware.py::test_downloaded_original_identity tests/test_ssm_firmware.py::test_unknown_files_are_never_whitelisted -q
```

Historisches Ergebnis dieser Fortsetzung (vor Ereignisumstellung): **55 bestanden, 0 fehlgeschlagen, 0 übersprungen**
(51 neue Fälle plus vier gezielt wiederholte Audit-Identitätsfälle).
Ohne Originaldateien bestehen die 24 neuen synthetischen Fälle; 27 neue
Originalprüfungen werden ausdrücklich übersprungen.
Python 3.12, Capstone 4.0.2, Unicorn 2.1.4, pytest 8. Die bekannte Capstone-
`pkg_resources`-Abkündigungswarnung bleibt. Der neue Testumfang umfasst
Containergrenzen, defekte Streams, Speicher-/Ausgabelimits, drei interne Hashes,
Instruktionsgrenzen, Timer-/IO-Verweise, echte Klick-/Langdruckroutinen,
Anzeigekopie/-aggregation und neun BLE-/MCU-Feldvergleiche.

Die zuvor dokumentierten 114 Tests wurden nicht vollständig erneut ausgeführt:
Zustandsmaschine, Demo, GUI, Exportblock und alte Speed-Patches sind unverändert.
Die 55 sind ein gezielter aktueller Lauf, keine neue Gesamtanzahl oder
Firmware-Codeabdeckungsangabe. Es gibt weiterhin null Hardwaretests.

| Hindernis | Präziser Stand |
| --- | --- |
| Lesbarkeit des BLE-APP | Softwareseitig gelöst: zwölf Blöcke, vollständiges APP, passende Hashes. ROM-Patch-Teilbereich bleibt separat ungeklärt. |
| Ursprünglicher Tastenpfad | Lokalisiert und isoliert mit Originalcode ausgeführt; Präfixkonflikt nachgewiesen. OEM-/SSM-Integration noch zu entwickeln. |
| Drei Modussymbole | Unabhängige Softwarebits bis zur Byte-Ausgabe belegt. Physische Symbolzuordnung und gemeinsames Dauerleuchten ungemessen. |
| Interner Modustransport | Builder und MCU-Feldkonsument zusammen geprüft. Gesamter Empfang, Gegenrichtung, Zeitverhalten und zusätzlicher SSM-Zustand offen. |
| Geeignete Hook-Semantik | Inzwischen fünf vollständige Instruktionen mit lokalen Verträgen identifiziert (siehe DOPPELKLICK.md). Kein sicherer Code-/RAM-Platz und kein injizierter Hook nachgewiesen. |

Weitere **Softwarearbeit** kann Kontrollfluss-/Speicherbelegung, vollständige
Protokollzustände, Region-/NVM-Lesen und einen integrierten Adapter untersuchen.
Diese offenen Punkte sind nicht automatisch durch Hardwaremessungen lösbar.

Zwingend **am realen Gerät zu messen** sind Tasterpegel/Prellen und tatsächliche
Schedulerlatenz, physische UART-Leitungen/Pegel/Baudrate und Fehlerverhalten,
Treiber-/Segmentzuordnung und gleichzeitige Anzeige mit Warnungen sowie
Worst-Case-Laufzeit, Strom-/Temperatur-/Brems-/Schutzreaktionen und App-Verhalten
bei echten Zustandswechseln. Eine Integration darf erst nach den fehlenden
Softwarebelegen und einem getrennt autorisierten Hardwaretestaufbau beurteilt
werden. Es wurde weder geflasht noch ein Sicherheitsmechanismus umgangen.

**Gesamtstatus bleibt Entwicklungsstufe 3.** Neu ist der nachvollziehbare
Offline-Nachweis ausgewählter Originalfunktionen; Stufe 4 setzt einen tatsächlich
integrierten und offline validierten SSM-Firmware-Patch voraus und ist nicht erreicht.
