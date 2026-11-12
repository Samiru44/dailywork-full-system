@echo off
title DailyWork - Full System
cd /d "%~dp0backend\DailyWork.Api"

echo =============================================================
echo   Starting DailyWork
echo.
echo   First run downloads packages - this may take a minute.
echo =============================================================
echo.

REM Remove the "downloaded from the internet" mark that Windows puts on files
REM extracted from a ZIP. Left in place it can make Application Control refuse
REM to run the build output. Harmless if there is nothing to unblock.
powershell -NoProfile -Command "Get-ChildItem -Path '%~dp0' -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue" >nul 2>&1

dotnet run

if errorlevel 1 (
    echo.
    echo =============================================================
    echo   The server did not start.
    echo.
    echo   "An Application Control policy has blocked this file"
    echo      Windows is blocking an unsigned program. Run this
    echo      instead, which starts the app through dotnet.exe:
    echo.
    echo         dotnet bin\Debug\net10.0\DailyWork.Api.dll
    echo.
    echo      See the Troubleshooting section of HOW-TO-RUN.md.
    echo.
    echo   "'dotnet' is not recognized"
    echo      The .NET 10 SDK is not installed, or this window was
    echo      opened before installing it. Install it, then open a
    echo      NEW terminal window.
    echo =============================================================
)

echo.
echo The server has stopped.
pause
