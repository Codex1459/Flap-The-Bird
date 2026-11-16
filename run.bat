@echo off
title Flap the Bird
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ===================================================
echo              FLAP THE BIRD LAUNCHER
echo ===================================================
echo.

:: 1. Check if Python is installed on the system
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not found in system PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    echo NOTE: Be sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Check if virtual environment exists; create it if missing
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment (.venv) not found.
    echo [INFO] Creating virtual environment (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment (.venv).
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created successfully.
    echo.
)

:: 3. Check and install required dependencies
".venv\Scripts\python.exe" -c "import PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing required dependencies from requirements.txt...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed successfully.
    echo.
)

:: 4. Auto-run the game
echo [INFO] Launching Flap the Bird...
echo.
".venv\Scripts\python.exe" main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] The game exited with an error.
    pause
)
