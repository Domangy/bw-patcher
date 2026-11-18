@echo off
setlocal
cd /d "%~dp0"
echo Mi5Pro: OFFLINE-TESTS der originalen Firmware
echo Es wird weder Firmware erstellt noch etwas auf den Scooter geschrieben.
echo.
poetry run python -m bwpatcher.mi5pro_offline_suite
set "status=%errorlevel%"
echo.
if "%status%"=="0" (
    echo PASS: Die Offline-Pruefung war erfolgreich.
) else (
    echo FEHLER: Die Offline-Pruefung ist nicht bestanden. Code: %status%
)
echo.
echo Bericht: originale\OFFLINE_PRUEFBERICHT.json
echo Keine Freigabe zum Flashen: Hierfuer fehlen weiterhin Hardwaretests.
pause
exit /b %status%
