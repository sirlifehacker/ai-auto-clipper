@echo off
setlocal EnableDelayedExpansion
title AI Auto Clipper — Setup
color 0A

echo.
echo  ============================================
echo   AI Auto Clipper — First-Time Setup
echo  ============================================
echo.
echo  This will take 5-10 minutes on first run.
echo  Please stay connected to the internet.
echo  Do NOT close this window.
echo.

:: ── 1. Download bundled Python runtime ────────────────────────────────────
if exist "python\python.exe" (
    echo [1/4] Python runtime already installed — skipping.
    goto :deps
)

echo [1/4] Downloading Python runtime (one-time, ~25 MB)...
powershell -NoProfile -Command ^
  "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile 'python_embed.zip' -UseBasicParsing"
if not exist "python_embed.zip" (
    echo.
    echo  ERROR: Download failed. Check your internet connection and try again.
    pause
    exit /b 1
)

echo  Extracting Python runtime...
powershell -NoProfile -Command ^
  "Expand-Archive -Path 'python_embed.zip' -DestinationPath 'python' -Force"
del /q python_embed.zip

:: Enable site-packages so pip and installed packages are found
powershell -NoProfile -Command ^
  "(Get-Content 'python\python311._pth') -replace '#import site','import site' | Set-Content 'python\python311._pth'"

:: Install pip into the bundled Python
echo  Installing pip into bundled Python...
powershell -NoProfile -Command ^
  "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py' -UseBasicParsing"
python\python.exe get-pip.py --quiet
del /q get-pip.py

echo  Python runtime ready  OK

:: ── 2. Install app dependencies ────────────────────────────────────────────
:deps
echo.
echo [2/4] Installing app dependencies (5-10 min, downloads ~1-2 GB)...
echo  Packages: Streamlit, yt-dlp, Whisper, Gemini, FFmpeg, and more.
echo.
python\python.exe -m pip install --upgrade pip --quiet
python\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  ERROR: Dependency installation failed.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)
echo  Dependencies installed  OK

:: ── 3. Set up .env config file ─────────────────────────────────────────────
echo.
echo [3/4] Setting up configuration...
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo  Configuration file created  OK
) else (
    echo  Configuration file already exists  OK
)

:: ── 4. Done ────────────────────────────────────────────────────────────────
echo.
echo [4/4] Setup complete!
echo.
echo  ============================================
echo   Installation successful!
echo  ============================================
echo.
echo  To launch the app, double-click:
echo    "Start AI Auto Clipper.bat"
echo.
pause
endlocal
