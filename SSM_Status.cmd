@echo off
cd /d "%~dp0"
poetry run python -m bwpatcher.ssm_readiness --output originale\SSM_STATUS.json
if errorlevel 1 echo Fehler bei der Pruefung. Details in der Konsole.
echo.
echo Pruefbericht: originale\SSM_STATUS.json
echo Dies ist keine Firmware. Es erfolgt KEIN Flash-Vorgang.
pause
