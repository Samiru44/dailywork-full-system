@echo off
title DailyWork - Brevo SMTP
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0START-DAILYWORK-BREVO.ps1"
if errorlevel 1 (
  echo.
  echo Brevo setup or DailyWork startup failed. Read the message above.
  pause
)
