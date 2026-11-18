@echo off
setlocal
cd /d "%~dp0"
echo Mi5Pro: OFFLINE-TESTS der originalen Firmware
echo Es wird weder Firmware erstellt noch etwas auf den Scooter geschrieben.
echo.
set "ORIGINAL_DIR=%~dp0originale"
if defined MI5PRO_FIRMWARE_DIR set "ORIGINAL_DIR=%MI5PRO_FIRMWARE_DIR%"
if not exist "%ORIGINAL_DIR%\ble_2.7.0_0015.bin" if exist "%~dp0..\bw-patcher\originale\ble_2.7.0_0015.bin" set "ORIGINAL_DIR=%~dp0..\bw-patcher\originale"
echo Geprueftes Originalverzeichnis: %ORIGINAL_DIR%
poetry run python -m bwpatcher.mi5pro_offline_suite --originale "%ORIGINAL_DIR%"
set "status=%errorlevel%"
echo.
if "%status%"=="0" (
    echo PASS: Die Offline-Pruefung war erfolgreich.
) else (
    echo FEHLER: Die Offline-Pruefung ist nicht bestanden. Code: %status%
)
echo.
echo Bericht: %ORIGINAL_DIR%\OFFLINE_PRUEFBERICHT.json
echo Keine Freigabe zum Flashen: Hierfuer fehlen weiterhin Hardwaretests.
pause
exit /b %status%
