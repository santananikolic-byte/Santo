@echo off
title PC-Doktor
rem Startet den PC-Doktor mit Administratorrechten.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Frage nach Administratorrechten ... bitte mit JA bestaetigen.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0PC-Doktor.ps1"
pause
