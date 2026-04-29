@echo off
setlocal EnableDelayedExpansion
title AI Auto Clipper
color 0A

echo.
echo  ============================================
echo   AI Auto Clipper — Starting...
echo  ============================================
echo.

:: ── Guard: venv must exist ─────────────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo  ERROR: App is not installed yet.
    echo.
    echo  Please run "install.bat" first.
    echo.
    pause
    exit /b 1
)

:: ── Guard: .env must exist ─────────────────────────────────────────────────
if not exist ".env" (
    echo  WARNING: No .env config file found.
    echo  Copying from .env.example — edit it to add your API keys.
    copy ".env.example" ".env" >nul
)

:: ── Find a free port (default 8501, try up to 8510) ───────────────────────
set PORT=8501
:findport
netstat -an 2>nul | find ":%PORT% " >nul
if not errorlevel 1 (
    set /a PORT+=1
    if !PORT! GTR 8510 (
        echo  ERROR: No free port found between 8501-8510.
        pause
        exit /b 1
    )
    goto findport
)

:: ── Launch Streamlit in background ────────────────────────────────────────
echo  Starting app on http://localhost:!PORT!
echo  (This window must stay open while you use the app)
echo.
echo  To stop the app, close this window or press Ctrl+C.
echo.

start "" /B .venv\Scripts\python.exe -m streamlit run app.py ^
    --server.port !PORT! ^
    --server.headless true ^
    --browser.gatherUsageStats false ^
    --theme.base light ^
    2>&1

:: ── Wait for Streamlit to be ready, then open browser ─────────────────────
echo  Waiting for app to start...
set TRIES=0
:waitloop
timeout /t 2 /nobreak >nul
set /a TRIES+=1
.venv\Scripts\python.exe -c "import urllib.request; urllib.request.urlopen('http://localhost:!PORT!')" >nul 2>&1
if not errorlevel 1 goto ready
if !TRIES! LSS 20 goto waitloop

echo  App is taking longer than expected to start.
echo  Try opening http://localhost:!PORT! in your browser manually.
goto openbrowser

:ready
echo  App is ready!

:openbrowser
start "" "http://localhost:!PORT!"

echo.
echo  ============================================
echo   AI Auto Clipper is running
echo   Open: http://localhost:!PORT!
echo  ============================================
echo.
echo  Press any key to STOP the app and close.
echo.
pause >nul

:: ── Shut down Streamlit on exit ────────────────────────────────────────────
echo  Stopping app...
taskkill /f /im python.exe /fi "WINDOWTITLE eq streamlit*" >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":!PORT! "') do (
    taskkill /f /pid %%p >nul 2>&1
)
echo  Done. Goodbye!
timeout /t 2 /nobreak >nul
endlocal
