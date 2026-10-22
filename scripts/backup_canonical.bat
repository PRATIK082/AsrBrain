@echo off
setlocal enabledelayedexpansion
rem ===========================================================================
rem  AsrBrain - back up the canonical store + local index before a migration
rem  (reversible migrations - back up before any DB migration).
rem
rem  Usage:
rem    scripts\backup_canonical.bat            back up data\canonical + data\indexes
rem    scripts\backup_canonical.bat <label>    add a label to the backup folder
rem
rem  Backups land in data\backups\<timestamp>[-label]\ and are never deleted
rem  by this script. Restore = copy the files back (see docs\rollback-guide.md).
rem ===========================================================================

cd /d "%~dp0.."

for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format 'yyyyMMdd-HHmmss'"`) do set "STAMP=%%T"
set "LABEL=%~1"
if defined LABEL (set "DEST=data\backups\%STAMP%-%LABEL%") else (set "DEST=data\backups\%STAMP%")

if not exist "data\canonical\canonical.db" (
    echo [error] data\canonical\canonical.db not found - nothing to back up.
    exit /b 1
)

mkdir "%DEST%" 2>nul
copy /y "data\canonical\canonical.db" "%DEST%\canonical.db" >nul
if errorlevel 1 (
    echo [error] backup copy failed.
    exit /b 1
)
if exist "data\indexes\hybrid.npz" copy /y "data\indexes\hybrid.npz" "%DEST%\" >nul
if exist "data\indexes\hybrid.meta.json" copy /y "data\indexes\hybrid.meta.json" "%DEST%\" >nul

echo [ok] backed up to %DEST%
for %%F in ("%DEST%\canonical.db") do echo      canonical.db: %%~zF bytes
goto :eof
