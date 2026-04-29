@echo off
setlocal EnableDelayedExpansion
title AI Auto Clipper — First-Time Setup
color 0A

echo.
echo  ============================================
echo   AI Auto Clipper — First-Time Setup
echo  ============================================
echo.

:: ── 1. Check Python ────────────────────────────────────────────────────────
echo [1/4] Checking for Python 3.11 or higher...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python was not found on this computer.
    echo.
    echo  Please install Python 3.11 from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: On the installer screen, tick the box
    echo  "Add Python to PATH" before clicking Install.
    echo.
    echo  After installing Python, run this file again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set PYMAJ=%%a
    set PYMIN=%%b
)
if !PYMAJ! LSS 3 (
    echo  ERROR: Python !PYVER! is too old. Please install Python 3.11+.
    pause
    exit /b 1
)
if !PYMAJ! EQU 3 if !PYMIN! LSS 11 (
    echo  ERROR: Python !PYVER! is too old. Please install Python 3.11+.
    pause
    exit /b 1
)
echo  Found Python !PYVER!  OK

:: ── 2. Create virtual environment ─────────────────────────────────────────
echo.
echo [2/4] Creating isolated Python environment (.venv)...
if exist ".venv\Scripts\python.exe" (
    echo  Already exists — skipping.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo  ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  Created .venv  OK
)

:: ── 3. Install dependencies ────────────────────────────────────────────────
echo.
echo [3/4] Installing dependencies (this may take 3-5 minutes)...
echo  Please wait — do not close this window.
echo.
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  ERROR: Dependency installation failed.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)
echo.
echo  Dependencies installed  OK

:: ── 4. Set up .env config ──────────────────────────────────────────────────
echo.
echo [4/4] Checking configuration file...
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo  ============================================
    echo   ACTION REQUIRED: Configure your API keys
    echo  ============================================
    echo.
    echo  A configuration file was created at:
    echo    %~dp0.env
    echo.
    echo  Please open that file in Notepad and fill in:
    echo    - GEMINI_API_KEY   (from Google AI Studio)
    echo    - GOOGLE_CLOUD_PROJECT  (your GCP project ID)
    echo    - Any other keys you want to enable
    echo.
    echo  After editing .env, run "Start AI Auto Clipper.bat"
    echo.
    start notepad "%~dp0.env"
) else (
    echo  .env already exists  OK
)

echo.
echo  ============================================
echo   Setup complete!
echo  ============================================
echo.
echo  To launch the app, double-click:
echo    "Start AI Auto Clipper.bat"
echo.
pause
endlocal
