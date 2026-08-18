@echo off
REM =====================================================================
REM  Acervator launch wrapper (MEM-217 / Session 24 Phase 3a)
REM  ------------------------------------------------------------------
REM  Launches main.py with all stdout + stderr captured to a timestamped
REM  log file in %USERPROFILE%\.acervator_logs\. Captures the exit code
REM  so a silent vanish is at least TIMESTAMPED.
REM
REM  Usage:  run_acervator.bat
REM
REM  After the app exits (normally or by crash):
REM    %USERPROFILE%\.acervator_logs\console_YYYYMMDD_HHMMSS.log
REM  contains everything that would have printed to the console.
REM
REM  Correlate with:
REM    crash_YYYYMMDD_HHMMSS.log        (MEM-216 Python + Qt hooks)
REM    faulthandler_YYYYMMDD_HHMMSS.log (MEM-217 native crashes)
REM    heartbeat.txt                    (MEM-217 liveness)
REM =====================================================================

setlocal enabledelayedexpansion

REM --- Ensure the log directory exists ---
if not exist "%USERPROFILE%\.acervator_logs" (
    mkdir "%USERPROFILE%\.acervator_logs"
)

REM --- Build the timestamp: YYYYMMDD_HHMMSS ---
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value ^| find "="') do set DT=%%I
set STAMP=%DT:~0,8%_%DT:~8,6%
set LOG=%USERPROFILE%\.acervator_logs\console_%STAMP%.log

echo.
echo Acervator launching...
echo Console output is being captured to:
echo   %LOG%
echo.
echo If the app vanishes silently, check that file AND:
echo   %USERPROFILE%\.acervator_logs\crash_%STAMP%.log
echo   %USERPROFILE%\.acervator_logs\faulthandler_%STAMP%.log
echo.

REM --- Launch. Merge stderr into stdout. Tee to both the console AND the log.
REM     On Windows without a native tee, we use redirection to the file and
REM     tail -f in a separate window if you want real-time view.
python main.py > "%LOG%" 2>&1

set EXITCODE=%ERRORLEVEL%

REM --- Append the exit code to the log so "app vanishes" leaves a marker ---
echo. >> "%LOG%"
echo === Acervator exited at %DATE% %TIME% with code %EXITCODE% === >> "%LOG%"

echo.
echo Acervator exited with code %EXITCODE%.
if %EXITCODE% NEQ 0 (
    echo.
    echo === LAST 40 LINES OF CONSOLE LOG ===
    powershell -Command "Get-Content '%LOG%' -Tail 40"
    echo.
    echo === CHECK THESE FILES FOR ROOT CAUSE ===
    dir /b /o-d "%USERPROFILE%\.acervator_logs\crash_*.log" 2>nul | findstr /n "^" | findstr "^1:" | for /f "tokens=2 delims=:" %%F in ('more') do echo   %USERPROFILE%\.acervator_logs\%%F
    dir /b /o-d "%USERPROFILE%\.acervator_logs\faulthandler_*.log" 2>nul | findstr /n "^" | findstr "^1:" | for /f "tokens=2 delims=:" %%F in ('more') do echo   %USERPROFILE%\.acervator_logs\%%F
)

endlocal
pause
