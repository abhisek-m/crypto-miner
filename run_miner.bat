@echo off
setlocal enabledelayedexpansion
title Crypto Pool Miner & Hardware Controller
chcp 65001 >nul 2>&1
color 0A
cls

:: Ensure current working directory is this script's directory
cd /d "%~dp0"

echo ========================================================================
echo               CRYPTO POOL MINER ^& HARDWARE CONTROLLER
echo ========================================================================
echo.

:: Check Python installation
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found in your system PATH!
    echo Please install Python 3.8 or newer from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Run the miner controller
python miner\miner_controller.py %*

if %errorlevel% neq 0 (
    echo.
    echo [!] Miner exited with status code: %errorlevel%
    pause
)

