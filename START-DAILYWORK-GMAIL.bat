@echo off
title DailyWork - Gmail SMTP
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0START-DAILYWORK-GMAIL.ps1"
if errorlevel 1 (
  echo.
  echo Gmail setup or DailyWork startup failed. Read the message above.
  pause
)
