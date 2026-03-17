@echo off
title ZeroDay Weekly - Launcher
color 0A

echo.
echo  ========================================
echo    ZeroDay Weekly ^| Starting Services
echo  ========================================
echo.

REM --- Web Server ---
echo  [1/1] Starting Web Server on http://localhost:8000 ...
start "ZeroDay Weekly - Web Server" cmd /k "cd /d %~dp0web && echo Web Server starting... && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 2 /nobreak >nul

echo.
echo  ----------------------------------------
echo   All services launched!
echo   Web:  http://localhost:8000
echo   Admin: http://localhost:8000/lifeng
echo  ----------------------------------------
echo.
echo  Close the opened windows to stop the services.
echo.
pause
