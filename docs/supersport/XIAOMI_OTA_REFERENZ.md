# Xiaomi 5 Pro: Originaldateien aus Xiaomi Cloud (18.11.2026)

## Quelle und Identität

Der Nutzer hat sich mit seinem eigenen Xiaomi-Home-Konto am Xiaomi-Cloud-API
angemeldet. Das eigene Gerät wurde in Cloudregion `de` unter der Modellkennung
`xiaomi.scooter.5pro` ermittelt. Der Abruf von `/v2/device/latest_ver`
lieferte für dieses Gerät BLE `2.7.0_0015` und MCU `0007`.
Weder Geräte-ID noch Zugangsdaten werden ins Repository geschrieben.

Die BLE-Datei wurde über einen HTTPS-Link des Xiaomi-CDN abgerufen und
stimmte mit der in der Cloud angegebenen MD5-Prüfsumme überein:

| Datei | Bytes | MD5 | SHA-256 |
| --- | ---: | --- | --- |
| Cloud-OTA-Download, unverändert | 153890 | `0d41b4df91f8d37b5f1355484e2b93c3` | `f8c801d50d36e258fda04f31d28276e2b576b227d32c7f356d9f98dac062e64e` |
| Erster BLE-Firmwarecontainer | 152552 | `1c76ba994d8326dca0203a424dc09ff6` | `061d34cac06fb31d93ff8f47650cd09d61fa46e7a883b35c23f35cabff1e6df7` |
| Original MCU 0007 | 149504 | `aabaad0de541d7c79ca24d28c45ba097` | `ddcd65400c4fbdb45cb4cdbec2e812026d7bc6cb755fd9dd0180800caed5f9b8` |

Der **erste BLE-Container entspricht Byte für Byte** dem bereits in den
Forschungsberichten untersuchten Original; auch sein dekomprimiertes APP
hat den erwarteten SHA-256-Wert
`95edba0d2d4a46405bfbb1a433b7ad4c1c72fc1787bc76eefe99a727c711bbae`.

Das Cloud-OTA-Paket hat **1338 weitere Bytes** hinter dem vollständigen
BLE-Container. Die lesende Sichtprüfung findet darin die ASCII-Modellkennung
`xiaomi.scooter.5pro` sowie **zwei PEM-Zertifikatsabschnitte**
(`BEGIN CERTIFICATE` / `END CERTIFICATE`). Das Format des gesamten Anhangs,
die genaue Zuordnung zu einer Signatur und die herstellerseitige Vertrauenskette
sind **nicht** unabhängig verifiziert. Insbesondere ist das bytegenaue
Abtrennen für die Analyse **keine** Freigabe, den abgetrennten Container als
vollständiges OTA-Update zu installieren. Die separierte Datei wird nur als
**exakte Grundlage für Offline-Analysen**, nicht als vollständiges
Hersteller-Updatepaket oder flashbare SSM-Firmware bezeichnet.

## Reproduzierbare Offline-Extraktion

Der Xiaomi-Cloud-Download liegt privat ausserhalb des Git-Repositories.
Nur nach exakter Prüfung von Länge, MD5, SHA-256, BLE-Containern und APP-Hash
trennt `bwpatcher.mi5pro_cloud` den bekannten Firmwarecontainer ab.

```powershell
cd C:\Users\dzirl\bw-patcher
poetry run python -m bwpatcher.mi5pro_cloud --input "C:\Users\dzirl\scooter-cloud-tools\quarantine\ble_from_xiaomi_cloud_de_0015.bin" --output ".\originale\ble_2.7.0_0015.bin"
```

Die Original-MCU befindet sich ebenfalls unter `originale/`; dieser
Ordner bleibt von Git ausgeschlossen. Keine Datei in diesem Ordner soll
versehentlich ins öffentliche Repository oder in einen Flash-Vorgang gelangen.

## Testlauf und verbleibende Grenzen

Mit `MI5PRO_FIRMWARE_DIR=originale` und
`MI5PRO_CLOUD_DOWNLOAD=<lokaler OTA-Pfad>` ergab der Testlauf unter
Windows/Poetry **400 passed, 1 warning**. Bei den Unicorn-Emulatortests
wurden vom Python-Faulthandler ausserdem 222 native
`Windows fatal exception: access violation`-Diagnosen protokolliert,
obwohl der Prozess mit Exit-Code 0 endete. Diese Meldungen müssen separat
untersucht werden; ein grüner Testlauf ist **kein Hardware-Sicherheitsnachweis**.

Die ausgeführten Originalanalyseberichte liegen lokal unter
`originale/integration_latest.json` und `originale/constraints_latest.json`.
Das sind **Analyseberichte**, keine Firmware und keine Installationsanleitung.

**Unverändert offen:** Firmware-Codeintegration, nachgewiesene private
BLE-RAM-/Codebereiche, robustes Aktivierungs-Intent, sichere Modusquittung,
Motor-Regler-/Brems-/Batterie- und Temperaturvalidierung, Herstellerformat/
Signaturakzeptanz, belastbare Rückfallstrategie sowie physische Hardwaretests.
Die Exportsperre für SSM bleibt bestehen. Es wurden weder Controller noch
Firmware auf dem Scooter verändert.
