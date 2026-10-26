@echo off
setlocal enabledelayedexpansion
rem ===========================================================================
rem  AsrBrain - restart the API on port 8000
rem
rem  Kills whatever currently holds port 8000 (and any orphaned uvicorn
rem  process started from this repository), waits until the port is really
rem  free, then starts a fresh uvicorn.
rem
rem  Usage:
rem    dev-api.bat          start uvicorn in this window (logs visible)
rem    dev-api.bat bg       start uvicorn detached, then poll /health
rem    dev-api.bat stop     stop the API and exit
rem ===========================================================================

cd /d "%~dp0"

set "PORT=8000"
set "HEALTH=http://127.0.0.1:%PORT%/health"

echo.
echo  AsrBrain API launcher  (repo: %CD%)
echo  ---------------------------------------------
echo.

if /i "%~1"=="stop" goto :stop
if /i "%~1"=="bg"   goto :background

rem --- 1. free the port --------------------------------------------------------
call :kill_port %PORT%
call :kill_uvicorn
call :wait_free %PORT% 30
if errorlevel 1 goto :failed

echo  [ok] port %PORT% is free.
echo.
echo  Starting:  python -m uvicorn apps.api.main:app --port %PORT%
echo  ---------------------------------------------
echo.
python -m uvicorn apps.api.main:app --port %PORT%
goto :eof

rem --- detached mode -----------------------------------------------------------
:background
call :kill_port %PORT%
call :kill_uvicorn
call :wait_free %PORT% 30
if errorlevel 1 goto :failed

echo  [ok] port %PORT% is free - starting uvicorn detached.
set "LOG=%TEMP%\asrbrain-api.log"
start "AsrBrain API :%PORT%" /min cmd /s /c ""python" -m uvicorn apps.api.main:app --port %PORT% > "%LOG%" 2>&1"

set /a tries=0
:health_loop
set "BODY="
for /f "usebackq delims=" %%B in (`curl.exe -s --max-time 5 "%HEALTH%" 2^>nul`) do set "BODY=%%B"
if defined BODY (
    echo  [ok] API is up: %BODY%
    echo  Logs: %LOG%
    goto :eof
)
set /a tries+=1
if !tries! gtr 45 (
    echo  [warn] the API did not answer /health within 90 s.
    echo  Check %LOG%
    exit /b 1
)
timeout /t 2 /nobreak >nul 2>&1
goto :health_loop

rem --- stop only --------------------------------------------------------------
:stop
call :kill_port %PORT%
call :kill_uvicorn
echo  [ok] the API on port %PORT% has been stopped.
goto :eof

rem --- routines ---------------------------------------------------------------
:kill_port
rem  kill every process that holds a LISTENING socket on the given port
set "P=%~1"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%P%[^0-9].*LISTENING" 2^>nul') do (
    echo  [kill] port %P% held by PID %%P
    taskkill /F /PID %%P >nul 2>&1
)
goto :eof

:kill_uvicorn
rem  kill orphaned uvicorn processes for this repository that did not bind
rem  (for example a process that is still starting up)
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" -ErrorAction SilentlyContinue ^| Where-Object { $_.CommandLine -like '*uvicorn*apps.api.main*' } ^| ForEach-Object { $_.ProcessId }" 2^>nul`) do (
    echo  [kill] orphaned uvicorn PID %%P
    taskkill /F /PID %%P >nul 2>&1
)
goto :eof

:wait_free
rem  wait until the port stops listening, up to %2 seconds
set "P=%~1"
set /a limit=%~2
set /a waited=0
:wf
set "BUSY="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%P%[^0-9].*LISTENING" 2^>nul') do set "BUSY=1"
if not defined BUSY goto :eof
set /a waited+=1
if !waited! gtr !limit! (
    echo  [error] port %P% is still in use after %limit% s.
    echo  Another process is holding it. Try running this file as Administrator,
    echo  or find it with:  netstat -ano ^| findstr :%P%
    exit /b 1
)
timeout /t 1 /nobreak >nul 2>&1
goto :wf

:failed
echo.
echo  Could not free port %PORT%. Nothing was started.
exit /b 1
